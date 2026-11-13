/*
 * GNSS single-shot fixes with A-GNSS.
 *
 * The nRF9160 shares one radio between LTE and GNSS: GNSS only runs while
 * LTE is idle (PSM / eDRX sleep / RRC idle). The report cycle therefore runs
 * GNSS while the modem sleeps and only then opens the LTE data session.
 */
#include <string.h>
#include <time.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/timeutil.h>
#include <nrf_modem_gnss.h>

#include "location.h"

LOG_MODULE_REGISTER(location, CONFIG_TRACKER_LOG_LEVEL);

/* Event bits, set from the GNSS callback (interrupt context). */
#define EVT_FIX     BIT(0)
#define EVT_TIMEOUT BIT(1)
#define EVT_AGNSS   BIT(2)
#define EVT_NO_SKY  BIT(3)

static K_EVENT_DEFINE(gnss_events);

static struct nrf_modem_gnss_pvt_data_frame last_fix;
static struct nrf_modem_gnss_agnss_data_frame agnss_need;

/* No-sky detection: start of the current search (reset after A-GNSS is
 * injected, since satellites only show up once the modem knows where to
 * look) and the best number of usable satellites seen in it.
 */
static int64_t search_start_ms;
static bool no_sky_posted;

/* Satellites received well enough to contribute to a fix. */
static uint8_t usable_satellites(const struct nrf_modem_gnss_pvt_data_frame *pvt)
{
	uint8_t n = 0;

	for (size_t i = 0; i < NRF_MODEM_GNSS_MAX_SATELLITES; i++) {
		if (pvt->sv[i].sv != 0 && pvt->sv[i].cn0 >= CONFIG_TRACKER_GNSS_NOSKY_CN0 * 10) {
			n++;
		}
	}
	return n;
}

static void gnss_event_handler(int event)
{
	/* Runs in IRQ context: copy out and signal, nothing else. */
	static struct nrf_modem_gnss_pvt_data_frame pvt;

	switch (event) {
	case NRF_MODEM_GNSS_EVT_PVT:
		if (nrf_modem_gnss_read(&pvt, sizeof(pvt), NRF_MODEM_GNSS_DATA_PVT) != 0) {
			break;
		}
		if (pvt.flags & NRF_MODEM_GNSS_PVT_FLAG_FIX_VALID) {
			last_fix = pvt;
			k_event_post(&gnss_events, EVT_FIX);
		} else if (CONFIG_TRACKER_GNSS_NOSKY_S > 0 && !no_sky_posted &&
			   k_uptime_get() - search_start_ms >= CONFIG_TRACKER_GNSS_NOSKY_S * MSEC_PER_SEC &&
			   usable_satellites(&pvt) < 3) {
			/* Indoors or covered: searching on only burns ~45 mA. */
			no_sky_posted = true;
			k_event_post(&gnss_events, EVT_NO_SKY);
		}
		break;
	case NRF_MODEM_GNSS_EVT_SLEEP_AFTER_TIMEOUT:
		k_event_post(&gnss_events, EVT_TIMEOUT);
		break;
	case NRF_MODEM_GNSS_EVT_AGNSS_REQ:
		if (nrf_modem_gnss_read(&agnss_need, sizeof(agnss_need),
					NRF_MODEM_GNSS_DATA_AGNSS_REQ) == 0) {
			k_event_post(&gnss_events, EVT_AGNSS);
		}
		break;
	default:
		break;
	}
}

int location_init(void)
{
	int err = nrf_modem_gnss_event_handler_set(gnss_event_handler);

	if (err) {
		LOG_ERR("Failed to set GNSS handler: %d", err);
	}

	return err;
}

int location_fix_start(uint16_t timeout_s)
{
	int err;

	k_event_clear(&gnss_events, EVT_FIX | EVT_TIMEOUT | EVT_AGNSS | EVT_NO_SKY);
	search_start_ms = k_uptime_get();
	no_sky_posted = false;

	/* fix_interval 0 == single fix; the receiver sleeps after the fix or
	 * after fix_retry seconds, whichever comes first.
	 */
	err = nrf_modem_gnss_fix_interval_set(0);
	err = err ? err : nrf_modem_gnss_fix_retry_set(timeout_s);
	/* MULTIPLE_HOT_START: keep ephemerides fresh between fixes.
	 * LOW_ACCURACY: accept a fix from fewer satellites (3 + reference
	 * altitude) - tens of metres is ample for a pet, and saves seconds.
	 */
	err = err ? err : nrf_modem_gnss_use_case_set(NRF_MODEM_GNSS_USE_CASE_MULTIPLE_HOT_START |
						      NRF_MODEM_GNSS_USE_CASE_LOW_ACCURACY);
	err = err ? err : nrf_modem_gnss_nmea_mask_set(0);
	err = err ? err : nrf_modem_gnss_start();

	if (err) {
		LOG_ERR("GNSS start failed: %d", err);
	}

	return err;
}

void location_assistance_injected(void)
{
	search_start_ms = k_uptime_get();
}

int location_stop(void)
{
	return nrf_modem_gnss_stop();
}

enum location_evt location_wait(k_timeout_t timeout)
{
	uint32_t evts = k_event_wait(&gnss_events, EVT_FIX | EVT_TIMEOUT | EVT_AGNSS | EVT_NO_SKY,
				     false, timeout);

	/* Consume one event per call, highest priority first. */
	if (evts & EVT_FIX) {
		k_event_clear(&gnss_events, EVT_FIX);
		return LOCATION_EVT_FIX;
	}
	if (evts & EVT_AGNSS) {
		k_event_clear(&gnss_events, EVT_AGNSS);
		return LOCATION_EVT_AGNSS_NEEDED;
	}
	if (evts & EVT_NO_SKY) {
		k_event_clear(&gnss_events, EVT_NO_SKY);
		return LOCATION_EVT_NO_SKY;
	}
	if (evts & EVT_TIMEOUT) {
		k_event_clear(&gnss_events, EVT_TIMEOUT);
		return LOCATION_EVT_TIMEOUT;
	}

	return LOCATION_EVT_NONE;
}

void location_fix_get(struct tracker_fix *fix)
{
	const struct nrf_modem_gnss_datetime *dt = &last_fix.datetime;
	struct tm tm = {
		.tm_year = dt->year - 1900,
		.tm_mon = dt->month - 1,
		.tm_mday = dt->day,
		.tm_hour = dt->hour,
		.tm_min = dt->minute,
		.tm_sec = dt->seconds,
	};

	fix->lat = last_fix.latitude;
	fix->lng = last_fix.longitude;
	fix->accuracy_m = last_fix.accuracy;
	fix->ts = timeutil_timegm64(&tm);

	LOG_INF("Fix: %.6f, %.6f (±%.0f m) in %u ms", fix->lat, fix->lng,
		(double)fix->accuracy_m, last_fix.execution_time);
}

const struct nrf_modem_gnss_agnss_data_frame *location_agnss_request(void)
{
	return &agnss_need;
}

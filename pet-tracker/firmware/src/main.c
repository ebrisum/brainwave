/*
 * Pet tracker - application state machine.
 *
 *            motion start                       still for N min
 *  STATIONARY ------------> MOVING ---------------------------> STATIONARY
 *  (4 h check-in, no GNSS)  (report every 15 min)
 *
 * Every report runs the same low-power sequence, with the power policy
 * (policy.c) deciding what is actually worth the energy:
 *   1. GNSS single fix while LTE sleeps in PSM - unless the pet hasn't moved
 *      since the last fix, or recent searches found no sky (backoff). A
 *      search without usable satellites stops after ~15 s, not 90 s. If the
 *      modem asks for assistance data, a short MQTT exchange fetches A-GNSS
 *      and RAI hands the radio straight back to GNSS.
 *   2. One MQTT/TLS session - unless the news can wait: positions inside a
 *      home zone are batched (4 fixes / 1 h), routine uploads wait out very
 *      poor coverage. Leaving or entering a zone, lost mode and positions
 *      away from home always go at once. The backlog goes up in batch
 *      messages; without a new fix a tiny heartbeat goes instead.
 *   3. RAI + DISCONNECT: modem returns to PSM (~3 uA), application core to
 *      System ON idle; nothing runs until a timer or the accelerometer fires.
 */
#include <stdio.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/reboot.h>
#include <zephyr/task_wdt/task_wdt.h>

#include "battery.h"
#include "cloud.h"
#include "fota.h"
#include "location.h"
#include "modem.h"
#include "motion.h"
#include "tracker.h"

LOG_MODULE_REGISTER(tracker, CONFIG_TRACKER_LOG_LEVEL);

#define LOST_MODE_INTERVAL_S      60
#define MIN_REPORT_SPACING_MS     (2 * MSEC_PER_SEC * 60)
#define NETWORK_WAIT              K_SECONDS(60)
#define DOWNLINK_DRAIN_MS         1000

enum app_state {
	STATE_STATIONARY,
	STATE_MOVING,
};

enum app_evt {
	EVT_REPORT_DUE,
	EVT_MOTION_START,
	EVT_MOTION_STOP,
};

K_MSGQ_DEFINE(app_msgq, sizeof(enum app_evt), 8, 4);

static enum app_state state = STATE_MOVING;
static struct tracker_config config = {
	.moving_interval_s = CONFIG_TRACKER_MOVING_INTERVAL_S,
	.lost_mode = false,
	.night_mode = false,
	.night_start_utc_min = 19 * 60,
	.night_end_utc_min = 5 * 60,
	.night_interval_s = 300,
};
static char device_id[TRACKER_DEVICE_ID_LEN];
static int wdt_channel = -1;
static int64_t last_report_ms = INT64_MIN / 2;
static uint32_t fix_seq;

/* Power policy state (see policy.h). */
static struct gnss_backoff gnss_backoff;
static bool has_accelerometer;
static bool moved_since_fix = true;  /* nothing known after boot */
static bool have_fix;
static struct tracker_fix last_good_fix;
static int64_t last_good_fix_ms;
static bool missed_motion;           /* a check fix found the pet elsewhere */
static enum zone_place last_place = PLACE_UNKNOWN;
static bool contacted;               /* a session succeeded since boot */
static int64_t last_contact_ms;

static const struct upload_cfg upload_cfg = {
	.home_batch = CONFIG_TRACKER_HOME_BATCH,
	.home_max_age_ms = (int64_t)CONFIG_TRACKER_HOME_MAX_AGE_S * MSEC_PER_SEC,
	.contact_max_ms = (int64_t)CONFIG_TRACKER_CONTACT_MAX_S * MSEC_PER_SEC,
};

/* --------------------------------------------------------------------------
 * Store-and-forward backlog (RAM ring buffer; oldest entry dropped when full)
 * -------------------------------------------------------------------------- */
static struct tracker_fix backlog[CONFIG_TRACKER_BACKLOG_SIZE];
static int64_t backlog_queued_ms[CONFIG_TRACKER_BACKLOG_SIZE]; /* uptime when queued */
static size_t backlog_head;
static size_t backlog_count;

static void backlog_push(const struct tracker_fix *fix)
{
	size_t tail = (backlog_head + backlog_count) % ARRAY_SIZE(backlog);

	if (backlog_count == ARRAY_SIZE(backlog)) {
		backlog_head = (backlog_head + 1) % ARRAY_SIZE(backlog);
		backlog_count--;
	}

	backlog[tail] = *fix;
	backlog_queued_ms[tail] = k_uptime_get();
	backlog_count++;
}

static int64_t backlog_oldest_ms(void)
{
	return backlog_count ? backlog_queued_ms[backlog_head] : 0;
}

/* Copies up to max of the oldest fixes into out[] (the ring may wrap). */
static size_t backlog_take(struct tracker_fix *out, size_t max)
{
	size_t n = MIN(max, backlog_count);

	for (size_t i = 0; i < n; i++) {
		out[i] = backlog[(backlog_head + i) % ARRAY_SIZE(backlog)];
	}
	return n;
}

static void backlog_drop(size_t n)
{
	n = MIN(n, backlog_count);
	backlog_head = (backlog_head + n) % ARRAY_SIZE(backlog);
	backlog_count -= n;
}

/* --------------------------------------------------------------------------
 * Event sources
 * -------------------------------------------------------------------------- */
static void post(enum app_evt evt)
{
	if (k_msgq_put(&app_msgq, &evt, K_NO_WAIT)) {
		LOG_WRN("Event queue full, dropping %d", evt);
	}
}

static void report_timer_handler(struct k_timer *timer)
{
	ARG_UNUSED(timer);
	post(EVT_REPORT_DUE);
}

K_TIMER_DEFINE(report_timer, report_timer_handler, NULL);

static void motion_handler(bool moving)
{
	post(moving ? EVT_MOTION_START : EVT_MOTION_STOP);
}

/* UTC clock derived from the last GNSS fix (the app core has no RTC sync). */
static int64_t utc_base_s = -1;
static int64_t utc_base_uptime_ms;

static void utc_sync(int64_t utc_s)
{
	utc_base_s = utc_s;
	utc_base_uptime_ms = k_uptime_get();
}

static bool night_watch_active(void)
{
	int64_t now_s;
	uint16_t minute;

	if (!config.night_mode || utc_base_s < 0) {
		return false;
	}

	now_s = utc_base_s + (k_uptime_get() - utc_base_uptime_ms) / MSEC_PER_SEC;
	minute = (uint16_t)((now_s / 60) % 1440);

	if (config.night_start_utc_min > config.night_end_utc_min) {
		/* window wraps midnight, e.g. 19:00-05:00 UTC */
		return minute >= config.night_start_utc_min || minute < config.night_end_utc_min;
	}
	return minute >= config.night_start_utc_min && minute < config.night_end_utc_min;
}

/* Seconds until the night window opens or closes (UINT32_MAX if unknown). */
static uint32_t seconds_to_night_edge(void)
{
	int64_t now_s;
	uint32_t minute, edge, delta_min;

	if (!config.night_mode || utc_base_s < 0) {
		return UINT32_MAX;
	}

	now_s = utc_base_s + (k_uptime_get() - utc_base_uptime_ms) / MSEC_PER_SEC;
	minute = (uint32_t)((now_s / 60) % 1440);
	edge = night_watch_active() ? config.night_end_utc_min : config.night_start_utc_min;
	delta_min = (edge + 1440 - minute) % 1440;

	return MAX(delta_min, 1U) * 60U;
}

static bool scheduled_night;

static void reschedule(void)
{
	uint32_t period_s;
	uint32_t first_s;
	bool night = night_watch_active();

	scheduled_night = night;

	if (config.lost_mode) {
		period_s = LOST_MODE_INTERVAL_S;
	} else if (state == STATE_MOVING) {
		period_s = night ? MIN(config.night_interval_s, config.moving_interval_s)
				 : config.moving_interval_s;
	} else {
		/* Resting, day or night: the accelerometer wakes us the moment
		 * the pet moves, so only a check-in is due.
		 */
		period_s = CONFIG_TRACKER_STATIONARY_INTERVAL_S;
	}

	/* Wake up at the night-window edge even during a long sleep interval. */
	first_s = MIN(period_s, seconds_to_night_edge());
	k_timer_start(&report_timer, K_SECONDS(first_s), K_SECONDS(period_s));
	LOG_INF("Next report in %u s, then every %u s%s", first_s, period_s, night ? " (night watch)" : "");
}

/* --------------------------------------------------------------------------
 * Cloud downlinks (invoked from within cloud_* calls, i.e. this thread)
 * -------------------------------------------------------------------------- */
static void config_handler(const struct tracker_config *cfg)
{
	if (cfg->lost_mode != config.lost_mode) {
		(void)modem_lost_mode_set(cfg->lost_mode);
		policy_gnss_reset(&gnss_backoff); /* search every cycle again */
	}
	if (cfg->zone_count != config.zone_count) {
		LOG_INF("%u home zone(s)", cfg->zone_count);
	}

	config = *cfg;
	reschedule();
}

static void fota_handler(const char *host, const char *path)
{
	(void)fota_start(host, path);
}

static const struct cloud_handlers cloud_handlers = {
	.config = config_handler,
	.fota = fota_handler,
};

/* --------------------------------------------------------------------------
 * Report cycle
 * -------------------------------------------------------------------------- */
static enum gnss_result acquire_fix(enum zone_place *place)
{
	/* Hard upper bound in case the modem never reports back. */
	const int64_t deadline = k_uptime_get() +
		(CONFIG_TRACKER_GNSS_TIMEOUT_S + CONFIG_TRACKER_AGNSS_WAIT_S + 30) * MSEC_PER_SEC;
	struct tracker_fix fix = { 0 };

	*place = PLACE_UNKNOWN;

	if (location_fix_start(CONFIG_TRACKER_GNSS_TIMEOUT_S)) {
		return GNSS_RESULT_TIMEOUT;
	}

	while (true) {
		int64_t remaining = deadline - k_uptime_get();
		enum location_evt evt = location_wait(K_MSEC(MAX(remaining, 0)));

		switch (evt) {
		case LOCATION_EVT_FIX: {
			int batt = battery_percent_get();

			location_fix_get(&fix);
			utc_sync(fix.ts);
			fix.seq = fix_seq++;
			fix.batt_pct = batt < 0 ? 0 : (uint8_t)batt;
			backlog_push(&fix);
			(void)location_stop();

			/* A check while "resting" that finds the pet far away:
			 * the accelerometer missed the movement.
			 */
			if (have_fix && !moved_since_fix &&
			    policy_moved_far(last_good_fix.lat, last_good_fix.lng, last_good_fix.accuracy_m,
					     fix.lat, fix.lng, fix.accuracy_m)) {
				LOG_WRN("Moved while marked as resting: switching to moving");
				missed_motion = true;
			}
			last_good_fix = fix;
			last_good_fix_ms = k_uptime_get();
			have_fix = true;
			moved_since_fix = false;
			*place = policy_zone_place(config.zones, config.zone_count, fix.lat, fix.lng,
						   fix.accuracy_m);
			return GNSS_RESULT_FIX;
		}
		case LOCATION_EVT_AGNSS_NEEDED:
			/* Ephemerides are valid ~4 h, so this happens rarely when
			 * moving and roughly once per heartbeat when stationary.
			 */
			if (modem_is_registered()) {
				struct modem_cell_info cell = { 0 };

				(void)modem_cell_info_get(&cell);
				if (cloud_agnss_fetch(location_agnss_request(), &cell)) {
					LOG_WRN("A-GNSS fetch failed, continuing unassisted");
				}
				/* Free the shared radio for GNSS immediately. */
				cloud_radio_release();
				location_assistance_injected();
			}
			break;
		case LOCATION_EVT_NO_SKY:
			LOG_INF("No sky (indoors?), GNSS stopped early");
			(void)location_stop();
			return GNSS_RESULT_NO_SKY;
		case LOCATION_EVT_TIMEOUT:
		case LOCATION_EVT_NONE:
		default:
			LOG_WRN("No GNSS fix this cycle");
			(void)location_stop();
			return GNSS_RESULT_TIMEOUT;
		}
	}
}

/*
 * gnss_note: why this cycle has no new fix ("still", "no_sky", ...), or NULL
 * if it has one. With nothing to upload, a heartbeat carries it instead.
 */
static void cloud_session(const char *gnss_note)
{
	struct tracker_fix batch[CLOUD_BATCH_MAX];
	bool published = false;
	int err;

	if (modem_wait_registered(NETWORK_WAIT)) {
		LOG_WRN("No LTE coverage, %u fix(es) buffered", (unsigned int)backlog_count);
		return;
	}

	err = cloud_connect();
	if (err) {
		LOG_WRN("Cloud unreachable (%d), %u fix(es) buffered", err,
			(unsigned int)backlog_count);
		return;
	}

	while (backlog_count > 0) {
		size_t n = backlog_take(batch, ARRAY_SIZE(batch));

		/* One fix keeps the original message (also understood by older
		 * backends); several go as one batch: one PUBACK round trip.
		 */
		err = n == 1 ? cloud_publish_fix(&batch[0]) : cloud_publish_fixes(batch, n);
		if (err) {
			LOG_WRN("Publish failed: %d", err);
			break;
		}
		backlog_drop(n);
		published = true;
	}

	if (!published && gnss_note && backlog_count == 0) {
		int batt = battery_percent_get();

		published = cloud_publish_heartbeat(batt < 0 ? 0 : (uint8_t)batt, gnss_note) == 0;
	}

	if (published) {
		contacted = true;
		last_contact_ms = k_uptime_get();
		/* A fresh image has proven it can boot, attach and talk TLS. */
		fota_confirm_image();
	}

	/* Queued downlinks from the persistent session arrive right after
	 * CONNACK; give stragglers a moment, then hang up.
	 */
	(void)cloud_poll(DOWNLINK_DRAIN_MS);
	cloud_disconnect();
}

static bool is_routine(enum upload_reason reason)
{
	return reason == UPLOAD_OUTSIDE || reason == UPLOAD_NO_ZONES ||
	       reason == UPLOAD_BATCH_FULL || reason == UPLOAD_BATCH_AGE;
}

static void report(void)
{
	enum gnss_result result;
	enum zone_place place = PLACE_UNKNOWN;
	const char *gnss_note;
	enum upload_reason reason;
	struct upload_ctx ctx;
	int64_t now;

	if (fota_in_progress()) {
		return; /* the download owns the radio until it reboots */
	}

	now = k_uptime_get();
	last_report_ms = now;

	/* Without an accelerometer nothing says "hasn't moved": always look. */
	if (!has_accelerometer) {
		moved_since_fix = true;
	}

	if (policy_should_fix(&gnss_backoff, config.lost_mode, moved_since_fix, have_fix,
			      last_good_fix_ms, (int64_t)CONFIG_TRACKER_STILL_VERIFY_S * MSEC_PER_SEC, now)) {
		result = acquire_fix(&place);
		policy_gnss_result(&gnss_backoff, result, k_uptime_get());
		gnss_note = result == GNSS_RESULT_FIX ? NULL :
			    result == GNSS_RESULT_NO_SKY ? "no_sky" : "timeout";
	} else {
		gnss_note = (moved_since_fix || !have_fix) ? "skipped" : "still";
		LOG_INF("GNSS skipped (%s)", gnss_note);
	}
	task_wdt_feed(wdt_channel);

	if (missed_motion && state == STATE_STATIONARY) {
		state = STATE_MOVING;
		reschedule();
	}

	ctx = (struct upload_ctx){
		.lost_mode = config.lost_mode,
		.first_contact = !contacted,
		.missed_motion = missed_motion,
		.zones_known = config.zone_count > 0,
		.place = place,
		.prev_place = last_place,
		.backlog = backlog_count,
		.backlog_max = ARRAY_SIZE(backlog),
		.now_ms = k_uptime_get(),
		.oldest_unsent_ms = backlog_oldest_ms(),
		.last_contact_ms = last_contact_ms,
	};
	reason = policy_upload(&ctx, &upload_cfg);

	/* Only routine uploads may wait for better coverage, and the modem is
	 * only asked when that could change the decision.
	 */
	if (IS_ENABLED(CONFIG_TRACKER_COVERAGE_AWARE) && is_routine(reason) && modem_coverage_poor()) {
		ctx.coverage_poor = true;
		reason = policy_upload(&ctx, &upload_cfg);
	}

	if (place != PLACE_UNKNOWN) {
		last_place = place;
	}

	missed_motion = false;

	if (reason != UPLOAD_DEFER) {
		LOG_INF("Uploading (reason %d, %u fix(es))", reason, (unsigned int)backlog_count);
		cloud_session(gnss_note);
	} else {
		LOG_INF("Holding %u fix(es) for later", (unsigned int)backlog_count);
		cloud_disconnect(); /* in case an A-GNSS exchange opened a session */
	}

	/* Entering or leaving the night window changes the cadence. */
	if (night_watch_active() != scheduled_night) {
		reschedule();
	}
}

/* --------------------------------------------------------------------------
 * Main
 * -------------------------------------------------------------------------- */
static void watchdog_init(void)
{
	const struct device *hw_wdt = DEVICE_DT_GET_OR_NULL(DT_ALIAS(watchdog0));

	if (task_wdt_init(device_is_ready(hw_wdt) ? hw_wdt : NULL)) {
		LOG_ERR("Task watchdog init failed");
		return;
	}

	/* No callback: an expired channel resets the SoC. */
	wdt_channel = task_wdt_add(CONFIG_TRACKER_WDT_TIMEOUT_S * MSEC_PER_SEC, NULL, NULL);
}

int main(void)
{
	char imei[16];
	int err;

	watchdog_init();

	err = modem_init();
	if (err) {
		LOG_ERR("Modem init failed (%d), rebooting in 60 s", err);
		k_sleep(K_SECONDS(60));
		sys_reboot(SYS_REBOOT_COLD);
	}

	if (modem_imei_get(imei, sizeof(imei)) == 0) {
		snprintf(device_id, sizeof(device_id), "pt-%s", imei);
	}
	LOG_INF("Device %s", device_id);

	(void)location_init();
	(void)fota_init();
	(void)cloud_init(device_id, &cloud_handlers);

	has_accelerometer = motion_init(motion_handler) == 0;
	if (!has_accelerometer) {
		LOG_WRN("No accelerometer: fixed-interval reporting, a fix every cycle");
	}

	/* First fix right after boot, then on schedule. */
	post(EVT_REPORT_DUE);
	reschedule();

	while (true) {
		enum app_evt evt;

		/* Wake at least twice per watchdog period to prove liveness. */
		if (k_msgq_get(&app_msgq, &evt,
			       K_SECONDS(CONFIG_TRACKER_WDT_TIMEOUT_S / 2)) == 0) {
			switch (evt) {
			case EVT_MOTION_START:
				moved_since_fix = true;
				if (state == STATE_STATIONARY) {
					LOG_INF("Moving");
					state = STATE_MOVING;
					/* A new outing: forget earlier "no sky" misses. */
					policy_gnss_reset(&gnss_backoff);
					reschedule();
					/* Owner sees the departure promptly, but
					 * jitter (a dog turning over) is rate-limited.
					 */
					if (k_uptime_get() - last_report_ms > MIN_REPORT_SPACING_MS) {
						report();
					}
				}
				break;
			case EVT_MOTION_STOP:
				if (state == STATE_MOVING) {
					LOG_INF("Stationary");
					state = STATE_STATIONARY;
					report(); /* resting position */
					reschedule();
				}
				break;
			case EVT_REPORT_DUE:
				report();
				break;
			}
		}

		task_wdt_feed(wdt_channel);
	}

	return 0;
}

#ifndef LOCATION_H_
#define LOCATION_H_

#include <zephyr/kernel.h>
#include <nrf_modem_gnss.h>

#include "tracker.h"

enum location_evt {
	LOCATION_EVT_NONE,
	LOCATION_EVT_FIX,           /* valid fix available: location_fix_get() */
	LOCATION_EVT_TIMEOUT,       /* GNSS gave up after the configured retry time */
	LOCATION_EVT_AGNSS_NEEDED,  /* modem asks for assistance: location_agnss_request() */
	LOCATION_EVT_NO_SKY,        /* searched TRACKER_GNSS_NOSKY_S without usable satellites */
};

int location_init(void);

/* Start a single-shot fix that the modem abandons after timeout_s. */
int location_fix_start(uint16_t timeout_s);

int location_stop(void);

/* A-GNSS was just injected: restart the no-sky clock for this search. */
void location_assistance_injected(void);

/* Wait for the next GNSS event of interest. */
enum location_evt location_wait(k_timeout_t timeout);

void location_fix_get(struct tracker_fix *fix);

/* Latest assistance-data need reported by the modem. */
const struct nrf_modem_gnss_agnss_data_frame *location_agnss_request(void);

#endif /* LOCATION_H_ */

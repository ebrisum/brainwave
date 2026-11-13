#ifndef CLOUD_H_
#define CLOUD_H_

#include <nrf_modem_gnss.h>

#include "modem.h"
#include "tracker.h"

struct cloud_handlers {
	void (*config)(const struct tracker_config *cfg);
	void (*fota)(const char *host, const char *path);
};

int cloud_init(const char *device_id, const struct cloud_handlers *handlers);

/* MQTT CONNECT over TLS 1.2 (mutual auth, session resumption). Idempotent. */
int cloud_connect(void);

/* Most fixes in one batch message (pt/v1/<id>/telemetry/batch). */
#define CLOUD_BATCH_MAX 8

/* QoS 1 publish of one fix; returns after PUBACK. */
int cloud_publish_fix(const struct tracker_fix *fix);

/* QoS 1 publish of up to CLOUD_BATCH_MAX consecutive fixes in one message. */
int cloud_publish_fixes(const struct tracker_fix *fixes, size_t n);

/*
 * "Alive, no new position": battery and why there is no fix
 * ("still": hasn't moved, "no_sky", "timeout", "skipped": backing off).
 */
int cloud_publish_heartbeat(uint8_t batt_pct, const char *gnss);

/* Ask the backend for A-GNSS data and inject the answer into the modem. */
int cloud_agnss_fetch(const struct nrf_modem_gnss_agnss_data_frame *need,
		      const struct modem_cell_info *cell);

/* Drain queued downlinks (config, FOTA) for up to timeout_ms. */
int cloud_poll(int timeout_ms);

/* Tell the network no more data is coming so RRC is released immediately. */
void cloud_radio_release(void);

void cloud_disconnect(void);

#endif /* CLOUD_H_ */

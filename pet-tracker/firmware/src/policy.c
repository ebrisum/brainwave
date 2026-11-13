/*
 * Power policy - see policy.h. Pure C: no Zephyr, no modem, no clock reads.
 */
#include <math.h>

#include "policy.h"

#define EARTH_RADIUS_M 6371000.0
#define DEG_TO_RAD     (3.14159265358979323846 / 180.0)

/* Equirectangular distance: exact enough below a few km, and cheap. */
static double distance_m(double lat1, double lng1, double lat2, double lng2)
{
	double x = (lng2 - lng1) * DEG_TO_RAD * cos((lat1 + lat2) * 0.5 * DEG_TO_RAD);
	double y = (lat2 - lat1) * DEG_TO_RAD;

	return sqrt(x * x + y * y) * EARTH_RADIUS_M;
}

enum zone_place policy_zone_place(const struct policy_zone *zones, size_t n,
				  double lat, double lng, float accuracy_m)
{
	bool near_edge = false;
	double acc = accuracy_m > 0 ? accuracy_m : 0;

	if (n == 0) {
		return PLACE_UNKNOWN;
	}

	for (size_t i = 0; i < n && i < POLICY_MAX_ZONES; i++) {
		double d = distance_m(lat, lng, zones[i].lat_e6 / 1e6, zones[i].lng_e6 / 1e6);
		double r = zones[i].radius_m;

		/* Same rule as the backend: inside if the whole uncertainty
		 * circle fits, outside if it doesn't touch the zone at all.
		 */
		if (d + acc <= r || (d <= r && acc <= r * 0.5)) {
			return PLACE_INSIDE;
		}
		if (d - acc <= r) {
			near_edge = true;
		}
	}

	return near_edge ? PLACE_EDGE : PLACE_OUTSIDE;
}

void policy_gnss_reset(struct gnss_backoff *b)
{
	b->streak = 0;
	b->skip_left = 0;
}

void policy_gnss_result(struct gnss_backoff *b, enum gnss_result r, int64_t now_ms)
{
	b->last_try_ms = now_ms;

	if (r == GNSS_RESULT_FIX) {
		policy_gnss_reset(b);
		return;
	}

	/* Skip 0, 1, 3, 7 cycles after 1, 2, 3, 4+ misses in a row. */
	if (b->streak < 4) {
		b->streak++;
	}
	b->skip_left = (uint8_t)((1u << (b->streak - 1)) - 1u);
}

bool policy_should_fix(struct gnss_backoff *b, bool lost_mode, bool moved_since_fix,
		       bool have_fix, int64_t now_ms)
{
	if (lost_mode) {
		return true; /* every position counts */
	}
	if (have_fix && !moved_since_fix) {
		return false; /* still where the last fix put it */
	}
	if (b->skip_left > 0 && now_ms - b->last_try_ms < POLICY_GNSS_MAX_GAP_MS) {
		b->skip_left--;
		return false;
	}
	return true;
}

enum upload_reason policy_upload(const struct upload_ctx *c, const struct upload_cfg *cfg)
{
	if (c->lost_mode) {
		return UPLOAD_LOST_MODE;
	}
	if (c->first_contact) {
		return UPLOAD_FIRST;
	}
	if (c->backlog >= c->backlog_max) {
		return UPLOAD_BACKLOG_FULL; /* or the oldest fix would be lost */
	}
	if (c->now_ms - c->last_contact_ms >= cfg->contact_max_ms) {
		return UPLOAD_CONTACT_DUE; /* heartbeat, downlinks, silent alert */
	}
	if (c->backlog == 0) {
		return UPLOAD_DEFER; /* nothing new, and contact isn't due */
	}
	if (!c->zones_known) {
		return UPLOAD_NO_ZONES;
	}

	/* Crossing a zone edge is the news owners wait for: always now. */
	bool out = c->place == PLACE_OUTSIDE || c->place == PLACE_EDGE;

	if (out && c->prev_place == PLACE_INSIDE) {
		return UPLOAD_CROSSED;
	}
	if (c->place == PLACE_INSIDE && c->prev_place != PLACE_INSIDE && c->prev_place != PLACE_UNKNOWN) {
		return UPLOAD_CROSSED; /* back home */
	}

	/* Bad coverage: a session can cost several times the normal energy.
	 * Keep routine positions for a better moment.
	 */
	if (c->coverage_poor) {
		return UPLOAD_DEFER;
	}
	if (out) {
		return UPLOAD_OUTSIDE;
	}
	if (c->backlog >= cfg->home_batch) {
		return UPLOAD_BATCH_FULL;
	}
	if (c->oldest_unsent_ms != 0 && c->now_ms - c->oldest_unsent_ms >= cfg->home_max_age_ms) {
		return UPLOAD_BATCH_AGE;
	}
	return UPLOAD_DEFER;
}

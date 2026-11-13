/*
 * Power policy: the decisions that decide battery life, kept free of Zephyr
 * and modem calls so they can be unit-tested on a PC (tests/host).
 *
 *  - Is a GNSS fix worth it this cycle? Not when the pet hasn't moved since
 *    the last good fix, and less often after GNSS found no sky (indoors).
 *  - Is an LTE session worth it now? Always for lost mode, for positions
 *    outside the home zones and for crossing a zone edge. Positions at home
 *    wait and go up together, at least every CONTACT_MAX, so the owner and
 *    the backend still hear from the collar regularly.
 */
#ifndef POLICY_H_
#define POLICY_H_

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define POLICY_MAX_ZONES 4

/* A home zone as sent by the backend: centre in micro-degrees, radius in m. */
struct policy_zone {
	int32_t lat_e6;
	int32_t lng_e6;
	uint16_t radius_m;
};

enum zone_place {
	PLACE_UNKNOWN,  /* no zones, or no fix */
	PLACE_INSIDE,   /* clearly inside a zone */
	PLACE_OUTSIDE,  /* clearly outside every zone */
	PLACE_EDGE,     /* within GPS uncertainty of an edge: treat as news */
};

/* Where a fix is relative to the zones, allowing for its accuracy. */
enum zone_place policy_zone_place(const struct policy_zone *zones, size_t n,
				  double lat, double lng, float accuracy_m);

/* --- GNSS: skip when pointless, back off after "no sky" ------------------ */

enum gnss_result {
	GNSS_RESULT_FIX,
	GNSS_RESULT_NO_SKY,   /* aborted early: no usable satellite signal */
	GNSS_RESULT_TIMEOUT,  /* searched the whole timeout without a fix */
};

struct gnss_backoff {
	uint8_t streak;        /* consecutive no-sky / timeout results */
	uint8_t skip_left;     /* cycles to skip before the next attempt */
	int64_t last_try_ms;
};

/* After this long without trying, try again whatever the backoff says. */
#define POLICY_GNSS_MAX_GAP_MS (60LL * 60 * 1000)

void policy_gnss_result(struct gnss_backoff *b, enum gnss_result r, int64_t now_ms);

/* Call when the situation changes (motion start after rest, lost mode): */
void policy_gnss_reset(struct gnss_backoff *b);

/*
 * Should this cycle run GNSS?
 *   moved_since_fix: the accelerometer saw motion since the last good fix
 *   have_fix:        there is a last good fix at all
 *   last_fix_ms:     when that fix was taken
 *   verify_ms:       even "unmoved", check the position after this long
 *                    (catches movement the accelerometer missed; 0 = never)
 * Consumes one skip when it says no because of the backoff.
 */
bool policy_should_fix(struct gnss_backoff *b, bool lost_mode, bool moved_since_fix,
		       bool have_fix, int64_t last_fix_ms, int64_t verify_ms, int64_t now_ms);

/*
 * Did the pet really move between two fixes? True when they are further
 * apart than both GPS uncertainties together plus a margin (and at least
 * 100 m): GPS wander of a sleeping cat never counts.
 */
bool policy_moved_far(double lat1, double lng1, float acc1, double lat2, double lng2, float acc2);

/* --- LTE: upload now or keep for the next session ------------------------ */

struct upload_ctx {
	bool lost_mode;
	bool first_contact;      /* nothing sent since boot */
	bool missed_motion;      /* a check fix found the pet far away while "resting" */
	bool zones_known;
	enum zone_place place;   /* of this cycle's fix (UNKNOWN without a fix) */
	enum zone_place prev_place; /* of the last fix before it */
	bool coverage_poor;      /* modem predicts an expensive session */
	size_t backlog;          /* fixes waiting, including this cycle's */
	size_t backlog_max;
	int64_t now_ms;
	int64_t oldest_unsent_ms; /* time of the oldest waiting fix (0: none) */
	int64_t last_contact_ms;  /* last successful session */
};

struct upload_cfg {
	size_t home_batch;         /* send at-home fixes in groups of this many */
	int64_t home_max_age_ms;   /* ...or when the oldest waits this long */
	int64_t contact_max_ms;    /* talk to the backend at least this often
				    * (battery level, downlinks, "silent" alert) */
};

enum upload_reason {
	UPLOAD_DEFER = 0,
	UPLOAD_LOST_MODE,
	UPLOAD_FIRST,
	UPLOAD_MISSED_MOTION,
	UPLOAD_NO_ZONES,
	UPLOAD_OUTSIDE,
	UPLOAD_CROSSED,
	UPLOAD_BATCH_FULL,
	UPLOAD_BATCH_AGE,
	UPLOAD_CONTACT_DUE,
	UPLOAD_BACKLOG_FULL,
};

enum upload_reason policy_upload(const struct upload_ctx *c, const struct upload_cfg *cfg);

#endif /* POLICY_H_ */

/*
 * Host tests for src/policy.c:  ./tests/host/run.sh
 */
#include <assert.h>
#include <stdio.h>

#include "../../src/policy.h"

#define MIN_MS (60LL * 1000)

static const struct policy_zone home[] = {
	{ .lat_e6 = 52379000, .lng_e6 = 4899500, .radius_m = 40 },
};

/* ~1 m of latitude is 1e-5 degrees * 1.11 */
static double north(double metres) { return 52.379 + metres / 111320.0; }

static void test_zone_place(void)
{
	assert(policy_zone_place(home, 0, 52.379, 4.8995, 5) == PLACE_UNKNOWN);
	assert(policy_zone_place(home, 1, north(10), 4.8995, 8) == PLACE_INSIDE);
	assert(policy_zone_place(home, 1, north(300), 4.8995, 8) == PLACE_OUTSIDE);
	/* 45 m out with +-15 m: could be either side of the edge */
	assert(policy_zone_place(home, 1, north(45), 4.8995, 15) == PLACE_EDGE);
	/* in the garden with a poor indoor fix: still home */
	assert(policy_zone_place(home, 1, north(15), 4.8995, 18) == PLACE_INSIDE);
	puts("ok - zone place with GPS uncertainty");
}

static void test_gnss_skip_when_still(void)
{
	struct gnss_backoff b = { 0 };

	const int64_t verify = 8 * 60 * MIN_MS;

	assert(!policy_should_fix(&b, false, false, true, 0, verify, 60 * MIN_MS)); /* asleep: keep last fix */
	assert(policy_should_fix(&b, false, true, true, 0, verify, 60 * MIN_MS));   /* moved: new fix */
	assert(policy_should_fix(&b, false, false, false, 0, verify, 60 * MIN_MS)); /* no fix yet: try */
	assert(policy_should_fix(&b, true, false, true, 0, verify, 60 * MIN_MS));   /* lost mode: always */
	puts("ok - no GNSS while the pet hasn't moved");

	/* Trust, but verify: after 8 h "unmoved", check anyway. */
	assert(!policy_should_fix(&b, false, false, true, 0, verify, verify - 1));
	assert(policy_should_fix(&b, false, false, true, 0, verify, verify));
	assert(!policy_should_fix(&b, false, false, true, 0, 0, 100 * verify)); /* verify off */
	puts("ok - a resting collar still checks its position every 8 h");
}

static void test_gnss_backoff(void)
{
	struct gnss_backoff b = { 0 };
	int64_t t = 0;
	int tries = 0;

	/* Moving indoors for 4 h at a 15 min interval, no sky at all. */
	for (int cycle = 0; cycle < 16; cycle++, t += 15 * MIN_MS) {
		if (policy_should_fix(&b, false, true, true, 0, 0, t)) {
			tries++;
			policy_gnss_result(&b, GNSS_RESULT_NO_SKY, t);
		}
	}
	assert(tries >= 4 && tries <= 7);   /* instead of 16 */
	printf("ok - indoors: %d GNSS attempts in 4 h instead of 16\n", tries);

	/* Never longer than an hour between attempts. */
	b.skip_left = 200;
	b.last_try_ms = 0;
	assert(policy_should_fix(&b, false, true, true, 0, 0, 61 * MIN_MS));

	/* A fix resets everything. */
	policy_gnss_result(&b, GNSS_RESULT_FIX, 0);
	assert(b.streak == 0 && b.skip_left == 0);
	puts("ok - backoff capped at an hour and reset by a fix");
}

static void test_moved_far(void)
{
	/* A sleeping cat: indoor GPS wanders 40 m with +-30 m: not a move. */
	assert(!policy_moved_far(52.379, 4.8995, 30, north(40), 4.8995, 30));
	/* Good fixes 80 m apart: under the 100 m floor (one garden). */
	assert(!policy_moved_far(52.379, 4.8995, 5, north(80), 4.8995, 5));
	/* 400 m away: the accelerometer missed it. */
	assert(policy_moved_far(52.379, 4.8995, 10, north(400), 4.8995, 10));
	/* Two bad fixes 150 m apart can't prove a move. */
	assert(!policy_moved_far(52.379, 4.8995, 60, north(150), 4.8995, 60));
	puts("ok - only a real distance counts as missed movement");
}

static const struct upload_cfg cfg = {
	.home_batch = 4,
	.home_max_age_ms = 60 * MIN_MS,
	.contact_max_ms = 120 * MIN_MS,
};

static struct upload_ctx at_home(void)
{
	return (struct upload_ctx){
		.zones_known = true, .place = PLACE_INSIDE, .prev_place = PLACE_INSIDE,
		.backlog = 1, .backlog_max = 32,
		.now_ms = 300 * MIN_MS, .oldest_unsent_ms = 300 * MIN_MS, .last_contact_ms = 290 * MIN_MS,
	};
}

static void test_upload(void)
{
	struct upload_ctx c = at_home();

	assert(policy_upload(&c, &cfg) == UPLOAD_DEFER);

	c.place = PLACE_OUTSIDE;
	assert(policy_upload(&c, &cfg) == UPLOAD_CROSSED); /* left home: now */
	c.prev_place = PLACE_OUTSIDE;
	assert(policy_upload(&c, &cfg) == UPLOAD_OUTSIDE); /* out and about: every fix */
	c.place = PLACE_EDGE;
	assert(policy_upload(&c, &cfg) == UPLOAD_OUTSIDE); /* unsure: tell the owner */
	c.place = PLACE_INSIDE;
	assert(policy_upload(&c, &cfg) == UPLOAD_CROSSED); /* back home: now */

	c = at_home();
	c.backlog = 4;
	assert(policy_upload(&c, &cfg) == UPLOAD_BATCH_FULL);
	c = at_home();
	c.oldest_unsent_ms = c.now_ms - 61 * MIN_MS;
	assert(policy_upload(&c, &cfg) == UPLOAD_BATCH_AGE);
	c = at_home();
	c.backlog = 0;
	c.last_contact_ms = c.now_ms - 121 * MIN_MS;
	assert(policy_upload(&c, &cfg) == UPLOAD_CONTACT_DUE); /* heartbeat */
	c.last_contact_ms = c.now_ms - 10 * MIN_MS;
	assert(policy_upload(&c, &cfg) == UPLOAD_DEFER);       /* nothing to say */

	c = at_home();
	c.lost_mode = true;
	assert(policy_upload(&c, &cfg) == UPLOAD_LOST_MODE);
	c = at_home();
	c.first_contact = true;
	assert(policy_upload(&c, &cfg) == UPLOAD_FIRST);
	c = at_home();
	c.missed_motion = true;
	c.coverage_poor = true;
	assert(policy_upload(&c, &cfg) == UPLOAD_MISSED_MOTION);
	c = at_home();
	c.zones_known = false;
	c.place = PLACE_UNKNOWN;
	assert(policy_upload(&c, &cfg) == UPLOAD_NO_ZONES);   /* old behaviour */
	puts("ok - home positions wait, leaving / coming home / lost mode go now");

	/* Poor coverage holds back the routine, never the urgent. */
	c = at_home();
	c.coverage_poor = true;
	c.place = PLACE_OUTSIDE;
	c.prev_place = PLACE_OUTSIDE;
	assert(policy_upload(&c, &cfg) == UPLOAD_DEFER);
	c.lost_mode = true;
	assert(policy_upload(&c, &cfg) == UPLOAD_LOST_MODE);
	c.lost_mode = false;
	c.prev_place = PLACE_INSIDE;
	assert(policy_upload(&c, &cfg) == UPLOAD_CROSSED); /* leaving home: still now */
	c.prev_place = PLACE_OUTSIDE;
	c.backlog = 32;
	assert(policy_upload(&c, &cfg) == UPLOAD_BACKLOG_FULL);
	puts("ok - poor coverage defers routine uploads only");
}

int main(void)
{
	test_zone_place();
	test_gnss_skip_when_still();
	test_gnss_backoff();
	test_moved_far();
	test_upload();
	puts("ALL POLICY TESTS PASSED");
	return 0;
}

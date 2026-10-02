// RidePrepLaneKeeper.h — engine-independent lane keeping (presentation physics), shared by the Unreal rider and the
// native test harness. Mirrors apps/client/src/engine/LaneKeeper.ts operation for operation; the cross-renderer test
// (apps/client/test/laneKeeper.cross.test.ts) feeds both the same ride and compares offset, yaw and lean.
//
// A trainer reports speed, not steering, so the rider cannot choose a line: this holds a realistic one inside the
// road "box" (keep right ~1 m from the edge, or a racing line on closed roads) and moves the bike there through a
// critically damped spring with lateral speed/acceleration caps, returning the matching yaw and lean; slow climbs get
// a pedal-synchronous weave. The physics distance along the route is untouched.
#pragma once

#include <algorithm>
#include <cmath>
#include <vector>

#include "RidePrepCourseMath.h"

namespace RidePrep {

class LaneKeeper {
public:
    enum class ELine { KeepRight, Racing };

    double Offset = 0;  // m, + = right of the route centreline
    double Yaw = 0;     // rad, bike heading relative to the road (+ = right)
    double Lean = 0;    // rad, extra lean from lateral acceleration (+ = right)
    ELine Line = ELine::KeepRight;

    explicit LaneKeeper(const RouteArrays& C, ELine InLine = ELine::KeepRight) : Line(InLine), R(&C) {
        Turn.assign(C.Count(), 0.0f);
        for (size_t I = 1; I < C.Count(); ++I) {
            const double D = double(C.HeadingRad[I]) - double(C.HeadingRad[I - 1]);
            Turn[I] = float(double(Turn[I - 1]) + std::atan2(std::sin(D), std::cos(D)));  // Float32Array semantics
        }
    }

    // Mean signed curvature over s ± w (1/m, + = bending right).
    double Curvature(double S, double W) const {
        const size_t A = Idx(S - W), B = Idx(S + W);
        return B > A ? (double(Turn[B]) - double(Turn[A])) / (double(B - A) * R->SpacingM) : 0.0;
    }

    // The line a rider would hold at s, riding at v m/s.
    double Target(double S, double V) const {
        const double Hw = double(R->RoadWidthM[Idx(S)]) / 2.0;
        if (Hw < 1.6) return 0.0;
        const double K = Curvature(S + std::max(5.0, V * 1.5), 15.0);
        const double Sharp = std::min(1.0, std::abs(K) * 40.0);
        if (Line == ELine::Racing) {
            const double Room = Hw - 0.6;
            return Room * (0.5 * (1.0 - Sharp) + Sign(K) * Sharp);
        }
        const double LaneC = Hw / 2.0;
        const double Edge = std::max(LaneC, Hw - 1.0);
        const double T = K > 0 ? Edge + (Hw - 0.7 - Edge) * Sharp : Edge + (LaneC - Edge) * Sharp;
        return std::max(0.3, std::min(Hw - 0.5, T));
    }

    // Advance by dt at route distance s, speed v (m/s) and crank angle (rad).
    void Update(double Dt, double S, double V, double CrankRad) {
        const double Goal = Target(S, V);
        if (!bStarted || Dt <= 0) {
            bStarted = true;
            Base = Goal;
            Offset = Goal;
            return;
        }
        const double W = 1.3;
        const double Acc = Clamp(W * W * (Goal - Base) - 2.0 * W * Vel, -1.2, 1.2);
        Vel += Acc * Dt;
        const double VMax = std::min(1.0, 0.18 * V);
        Vel = Clamp(Vel, -VMax, VMax);
        Base += Vel * Dt;
        const double Slow = Clamp((3.0 - V) / 1.8, 0.0, 1.0) * (V > 0.3 ? 1.0 : 0.0);
        const double NewWeave = Slow * 0.035 * std::sin(CrankRad);
        const double WeaveVel = (NewWeave - Weave) / Dt;
        Weave = NewWeave;
        Offset = Base + NewWeave;
        Yaw = V > 0.5 ? Clamp(std::atan2(Vel + WeaveVel, V), -0.12, 0.12) : 0.0;
        Lean += (std::atan(Acc / 9.81) - Lean) * std::min(1.0, Dt / 0.35);
    }

    // Jump straight to the line at s (teleports, restarts).
    void Reset() { bStarted = false; Vel = 0; Weave = 0; Yaw = 0; Lean = 0; }

private:
    const RouteArrays* R;
    std::vector<float> Turn;
    double Base = 0, Vel = 0, Weave = 0;
    bool bStarted = false;

    static double Clamp(double X, double Lo, double Hi) { return std::max(Lo, std::min(Hi, X)); }
    static double Sign(double X) { return double((X > 0) - (X < 0)); }
    // JavaScript Math.round (half up), so both sides pick the same sample
    size_t Idx(double S) const {
        const double I = std::floor(S / R->SpacingM + 0.5);
        const double Last = double(R->Count() - 1);
        return size_t(std::min(Last, std::max(0.0, I)));
    }
};

// Road surface height offset at a lateral offset (crown 2 % blended into superelevation, + bank = right edge lower).
// Mirrors crossSlopeDz in apps/client/src/engine/Road.ts and cs() in the Blender bakes.
inline double CrossSlopeDz(double OffsetM, double BankDeg, double Crown = 0.02) {
    const double T = std::tan(BankDeg * 3.141592653589793 / 180.0);
    const double W = std::min(1.0, std::abs(T) / 0.025);
    return (1 - W) * -Crown * std::abs(OffsetM) + W * -T * OffsetM;
}

}  // namespace RidePrep

// Prints LocalToLatLon / GridConvergenceDeg for "lat0 lon0 x y" lines on stdin (cross-check with the TS implementation).
#include "../Plugins/RidePrepRuntime/Source/RidePrepRuntime/Public/RidePrepCourseMath.h"
#include <cstdio>
#include <iostream>
int main() {
    double La0, Lo0, X, Y;
    while (std::cin >> La0 >> Lo0 >> X >> Y) {
        double La, Lo;
        RidePrep::LocalToLatLon(La0, Lo0, X, Y, La, Lo);
        std::printf("%.10f %.10f %.6f\n", La, Lo, RidePrep::GridConvergenceDeg(La0, Lo0, X, Y));
    }
}

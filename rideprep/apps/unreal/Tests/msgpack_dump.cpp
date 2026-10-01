// Decodes a MessagePack StreamState from stdin and prints key fields (used by the cross-language test).
#include "../Plugins/RidePrepRuntime/Source/RidePrepRuntime/Public/RidePrepMsgPack.h"
#include <cstdio>
#include <iostream>
#include <iterator>

int main() {
    std::vector<uint8_t> B((std::istreambuf_iterator<char>(std::cin)), std::istreambuf_iterator<char>());
    const RidePrep::MsgValue V = RidePrep::DecodeMsgPack(B.data(), B.size());
    const RidePrep::MsgValue* Wind = V.Get("wind");
    const RidePrep::MsgValue* Pos = V.Get("pos");
    std::printf("%s %.6f %.6f %.6f %.6f %d %.6f %.6f\n", V.StrAt("type").c_str(), V.NumAt("s"), V.NumAt("speed"), Pos ? Pos->A[0].Num() : -1, Pos ? Pos->A[2].Num() : -1,
                V.BoolAt("braking") ? 1 : 0, Wind ? Wind->NumAt("uRider") : -1, V.NumAt("seq"));
    return 0;
}

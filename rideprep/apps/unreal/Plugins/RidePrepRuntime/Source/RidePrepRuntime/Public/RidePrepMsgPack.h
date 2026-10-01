// RidePrepMsgPack.h — minimal, engine-independent MessagePack decoder for the ride-core state stream.
// Supports nil, bool, ints, float32/64, str, bin, array and map: everything @msgpack/msgpack emits for StreamState.
#pragma once

#include <cstdint>
#include <cstring>
#include <map>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

namespace RidePrep {

struct MsgValue {
    enum class Kind { Nil, Bool, Int, Float, Str, Bin, Array, Map } K = Kind::Nil;
    bool B = false;
    int64_t I = 0;
    double F = 0;
    std::string S;
    std::vector<MsgValue> A;
    std::map<std::string, MsgValue> M;

    double Num(double Default = 0) const { return K == Kind::Float ? F : K == Kind::Int ? double(I) : Default; }
    const MsgValue* Get(const std::string& Key) const {
        auto It = M.find(Key);
        return It == M.end() ? nullptr : &It->second;
    }
    double NumAt(const std::string& Key, double Default = 0) const { const MsgValue* V = Get(Key); return V ? V->Num(Default) : Default; }
    bool BoolAt(const std::string& Key) const { const MsgValue* V = Get(Key); return V && V->K == Kind::Bool && V->B; }
    std::string StrAt(const std::string& Key) const { const MsgValue* V = Get(Key); return V && V->K == Kind::Str ? V->S : std::string(); }
};

class MsgReader {
public:
    MsgReader(const uint8_t* D, size_t N) : Data(D), Size(N) {}
    MsgValue Read() {
        const uint8_t T = U8();
        MsgValue V;
        if (T <= 0x7f) { V.K = MsgValue::Kind::Int; V.I = T; return V; }
        if (T >= 0xe0) { V.K = MsgValue::Kind::Int; V.I = int8_t(T); return V; }
        if ((T & 0xf0) == 0x80) return ReadMap(T & 0x0f);
        if ((T & 0xf0) == 0x90) return ReadArray(T & 0x0f);
        if ((T & 0xe0) == 0xa0) return ReadStr(T & 0x1f);
        switch (T) {
            case 0xc0: return V;
            case 0xc2: V.K = MsgValue::Kind::Bool; V.B = false; return V;
            case 0xc3: V.K = MsgValue::Kind::Bool; V.B = true; return V;
            case 0xc4: return ReadBin(U8());
            case 0xc5: return ReadBin(BE<uint16_t>());
            case 0xc6: return ReadBin(BE<uint32_t>());
            case 0xca: { uint32_t R = BE<uint32_t>(); float Fv; std::memcpy(&Fv, &R, 4); V.K = MsgValue::Kind::Float; V.F = Fv; return V; }
            case 0xcb: { uint64_t R = BE<uint64_t>(); double Dv; std::memcpy(&Dv, &R, 8); V.K = MsgValue::Kind::Float; V.F = Dv; return V; }
            case 0xcc: V.K = MsgValue::Kind::Int; V.I = U8(); return V;
            case 0xcd: V.K = MsgValue::Kind::Int; V.I = BE<uint16_t>(); return V;
            case 0xce: V.K = MsgValue::Kind::Int; V.I = BE<uint32_t>(); return V;
            case 0xcf: V.K = MsgValue::Kind::Int; V.I = int64_t(BE<uint64_t>()); return V;
            case 0xd0: V.K = MsgValue::Kind::Int; V.I = int8_t(U8()); return V;
            case 0xd1: V.K = MsgValue::Kind::Int; V.I = int16_t(BE<uint16_t>()); return V;
            case 0xd2: V.K = MsgValue::Kind::Int; V.I = int32_t(BE<uint32_t>()); return V;
            case 0xd3: V.K = MsgValue::Kind::Int; V.I = int64_t(BE<uint64_t>()); return V;
            case 0xd9: return ReadStr(U8());
            case 0xda: return ReadStr(BE<uint16_t>());
            case 0xdb: return ReadStr(BE<uint32_t>());
            case 0xdc: return ReadArray(BE<uint16_t>());
            case 0xdd: return ReadArray(BE<uint32_t>());
            case 0xde: return ReadMap(BE<uint16_t>());
            case 0xdf: return ReadMap(BE<uint32_t>());
            default: throw std::runtime_error("unsupported msgpack type");
        }
    }

private:
    const uint8_t* Data;
    size_t Size;
    size_t Pos = 0;
    void Need(size_t N) { if (Pos + N > Size) throw std::runtime_error("truncated msgpack"); }
    uint8_t U8() { Need(1); return Data[Pos++]; }
    template <typename T> T BE() {
        Need(sizeof(T));
        T V = 0;
        for (size_t i = 0; i < sizeof(T); ++i) V = T((V << 8) | Data[Pos + i]);
        Pos += sizeof(T);
        return V;
    }
    MsgValue ReadStr(size_t N) { Need(N); MsgValue V; V.K = MsgValue::Kind::Str; V.S.assign(reinterpret_cast<const char*>(Data + Pos), N); Pos += N; return V; }
    MsgValue ReadBin(size_t N) { MsgValue V = ReadStr(N); V.K = MsgValue::Kind::Bin; return V; }
    MsgValue ReadArray(size_t N) { MsgValue V; V.K = MsgValue::Kind::Array; V.A.reserve(N); for (size_t i = 0; i < N; ++i) V.A.push_back(Read()); return V; }
    MsgValue ReadMap(size_t N) {
        MsgValue V;
        V.K = MsgValue::Kind::Map;
        for (size_t i = 0; i < N; ++i) {
            MsgValue Key = Read();
            V.M[Key.K == MsgValue::Kind::Str ? Key.S : std::to_string(Key.I)] = Read();
        }
        return V;
    }
};

inline MsgValue DecodeMsgPack(const uint8_t* Data, size_t Size) { return MsgReader(Data, Size).Read(); }

// Encodes a small command map {type: <str>, value?: <double>} for the socket back-channel.
inline std::vector<uint8_t> EncodeCommand(const std::string& Type, const std::string& ExtraKey = "", double Value = 0, const std::string& StrValue = "") {
    std::vector<uint8_t> Out;
    auto Str = [&](const std::string& S) { Out.push_back(uint8_t(0xa0 | S.size())); Out.insert(Out.end(), S.begin(), S.end()); };
    const bool HasExtra = !ExtraKey.empty();
    Out.push_back(uint8_t(0x80 | (HasExtra ? 2 : 1)));
    Str("type"); Str(Type);
    if (HasExtra) {
        Str(ExtraKey);
        if (!StrValue.empty()) Str(StrValue);
        else { Out.push_back(0xcb); uint64_t R; std::memcpy(&R, &Value, 8); for (int i = 7; i >= 0; --i) Out.push_back(uint8_t(R >> (i * 8))); }
    }
    return Out;
}

}  // namespace RidePrep

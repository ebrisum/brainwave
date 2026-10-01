#include "RidePrepStreamClient.h"

#include "IWebSocket.h"
#include "WebSocketsModule.h"
#include "RidePrepMsgPack.h"

void URidePrepStreamClient::Connect(const FString& Url)
{
    if (!FModuleManager::Get().IsModuleLoaded(TEXT("WebSockets"))) FModuleManager::Get().LoadModule(TEXT("WebSockets"));
    Socket = FWebSocketsModule::Get().CreateWebSocket(Url, TEXT(""));
    Socket->OnRawMessage().AddUObject(this, &URidePrepStreamClient::OnRaw);
    Socket->OnConnectionError().AddLambda([Url](const FString& Err) { UE_LOG(LogTemp, Warning, TEXT("RidePrep: cannot connect to %s: %s"), *Url, *Err); });
    Socket->Connect();
}

void URidePrepStreamClient::Disconnect()
{
    if (Socket.IsValid()) Socket->Close();
    Socket.Reset();
}

bool URidePrepStreamClient::IsConnected() const { return Socket.IsValid() && Socket->IsConnected(); }

void URidePrepStreamClient::OnRaw(const void* Data, SIZE_T Size, SIZE_T Remaining)
{
    Partial.Append(static_cast<const uint8*>(Data), (int32)Size);
    if (Remaining > 0) return;
    RidePrep::MsgValue V;
    try
    {
        V = RidePrep::DecodeMsgPack(Partial.GetData(), Partial.Num());
    }
    catch (...)
    {
        Partial.Reset();
        return;
    }
    Partial.Reset();
    const std::string Type = V.StrAt("type");
    if (Type == "hello")
    {
        OnHello.Broadcast(UTF8_TO_TCHAR(V.StrAt("courseId").c_str()), UTF8_TO_TCHAR(V.StrAt("packageUrl").c_str()));
        return;
    }
    if (Type != "state") return;
    FRidePrepStreamState S;
    S.Seq = (int64)V.NumAt("seq");
    S.SentAtMs = V.NumAt("sentAt");
    S.T = V.NumAt("t");
    S.S = V.NumAt("s");
    S.Speed = V.NumAt("speed");
    S.Power = V.NumAt("power");
    S.HeartRate = V.NumAt("hr");
    S.Cadence = V.NumAt("cadence");
    S.CrankAngle = V.NumAt("crank");
    S.Lean = V.NumAt("lean");
    S.bBraking = V.BoolAt("braking");
    S.GradePct = V.NumAt("gradePct");
    if (const RidePrep::MsgValue* W = V.Get("wind"))
    {
        S.Wind.U10 = W->NumAt("u10"); S.Wind.Dir10 = W->NumAt("dir10"); S.Wind.URider = W->NumAt("uRider"); S.Wind.DirRider = W->NumAt("dirRider");
        S.Wind.WHead = W->NumAt("wHead"); S.Wind.WCross = W->NumAt("wCross"); S.Wind.Gust = W->NumAt("gust", 1); S.Wind.Shelter = W->NumAt("shelter", 1);
    }
    if (const RidePrep::MsgValue* W = V.Get("weather"))
    {
        S.Weather.TempC = W->NumAt("tempC"); S.Weather.RH = W->NumAt("rh"); S.Weather.PMslHpa = W->NumAt("pMslHpa"); S.Weather.PrecipMmH = W->NumAt("precipMmH");
        S.Weather.CloudCover = W->NumAt("cloudCover"); S.Weather.VisibilityM = W->NumAt("visibilityM", 20000); S.Weather.Rho = W->NumAt("rho", 1.225);
    }
    if (const RidePrep::MsgValue* Sun = V.Get("sun")) { S.SunElevationDeg = Sun->NumAt("elevationDeg"); S.SunAzimuthDeg = Sun->NumAt("azimuthDeg"); }
    if (const RidePrep::MsgValue* H = V.Get("hud"))
    {
        S.Hud.NpW = H->NumAt("npW"); S.Hud.IntensityFactor = H->NumAt("ifactor"); S.Hud.WKg = H->NumAt("wkg"); S.Hud.Lap = (int32)H->NumAt("lap", 1);
        S.Hud.Laps = (int32)H->NumAt("laps", 1); S.Hud.AscentM = H->NumAt("ascentM"); S.Hud.TargetW = H->NumAt("targetW"); S.Hud.ElapsedS = H->NumAt("elapsedS");
        S.Hud.DistanceM = H->NumAt("distanceM");
    }
    S.bPaused = V.BoolAt("paused");
    S.bFinished = V.BoolAt("finished");
    S.ReceivedAt = FPlatformTime::Seconds();
    Previous = Latest;
    Latest = S;
}

double URidePrepStreamClient::InterpolatedS(double Now) const
{
    if (Latest.bPaused) return Latest.S;
    // Extrapolate from the latest state by at most one 20 ms step to hide network jitter
    const double Dt = FMath::Clamp(Now - Latest.ReceivedAt, 0.0, 0.05);
    return Latest.S + Latest.Speed * Dt;
}

void URidePrepStreamClient::Send(const std::vector<uint8_t>& Bytes)
{
    if (IsConnected()) Socket->Send(Bytes.data(), Bytes.size(), true);
}

void URidePrepStreamClient::SendPause(bool bPause) { Send(RidePrep::EncodeCommand(bPause ? "pause" : "resume")); }
void URidePrepStreamClient::SendEnd() { Send(RidePrep::EncodeCommand("end")); }
void URidePrepStreamClient::SendDifficulty(float Value) { Send(RidePrep::EncodeCommand("difficulty", "value", Value)); }
void URidePrepStreamClient::SendCamera(ERidePrepCamera Mode)
{
    static const char* Names[] = { "chase", "first", "side", "drone", "flyover" };
    Send(RidePrep::EncodeCommand("camera", "mode", 0, Names[(int32)Mode]));
}

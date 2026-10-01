#pragma once

#include "CoreMinimal.h"
#include "RidePrepTypes.generated.h"

/** Mirror of StreamState (packages/course-format/src/stream.ts). */
USTRUCT(BlueprintType)
struct FRidePrepWind
{
    GENERATED_BODY()
    UPROPERTY(BlueprintReadOnly) float U10 = 0;
    UPROPERTY(BlueprintReadOnly) float Dir10 = 0;
    UPROPERTY(BlueprintReadOnly) float URider = 0;
    UPROPERTY(BlueprintReadOnly) float DirRider = 0;
    UPROPERTY(BlueprintReadOnly) float WHead = 0;
    UPROPERTY(BlueprintReadOnly) float WCross = 0;
    UPROPERTY(BlueprintReadOnly) float Gust = 1;
    UPROPERTY(BlueprintReadOnly) float Shelter = 1;
};

USTRUCT(BlueprintType)
struct FRidePrepWeather
{
    GENERATED_BODY()
    UPROPERTY(BlueprintReadOnly) float TempC = 15;
    UPROPERTY(BlueprintReadOnly) float RH = 0.7f;
    UPROPERTY(BlueprintReadOnly) float PMslHpa = 1013;
    UPROPERTY(BlueprintReadOnly) float PrecipMmH = 0;
    UPROPERTY(BlueprintReadOnly) float CloudCover = 0.5f;
    UPROPERTY(BlueprintReadOnly) float VisibilityM = 20000;
    UPROPERTY(BlueprintReadOnly) float Rho = 1.225f;
};

USTRUCT(BlueprintType)
struct FRidePrepHud
{
    GENERATED_BODY()
    UPROPERTY(BlueprintReadOnly) float NpW = 0;
    UPROPERTY(BlueprintReadOnly) float IntensityFactor = 0;
    UPROPERTY(BlueprintReadOnly) float WKg = 0;
    UPROPERTY(BlueprintReadOnly) int32 Lap = 1;
    UPROPERTY(BlueprintReadOnly) int32 Laps = 1;
    UPROPERTY(BlueprintReadOnly) float AscentM = 0;
    UPROPERTY(BlueprintReadOnly) float TargetW = 0;
    UPROPERTY(BlueprintReadOnly) float ElapsedS = 0;
    UPROPERTY(BlueprintReadOnly) float DistanceM = 0;
};

USTRUCT(BlueprintType)
struct FRidePrepStreamState
{
    GENERATED_BODY()
    UPROPERTY(BlueprintReadOnly) int64 Seq = 0;
    UPROPERTY(BlueprintReadOnly) double SentAtMs = 0;
    UPROPERTY(BlueprintReadOnly) double T = 0;
    UPROPERTY(BlueprintReadOnly) double S = 0;
    UPROPERTY(BlueprintReadOnly) float Speed = 0;
    UPROPERTY(BlueprintReadOnly) float Power = 0;
    UPROPERTY(BlueprintReadOnly) float HeartRate = 0;
    UPROPERTY(BlueprintReadOnly) float Cadence = 0;
    UPROPERTY(BlueprintReadOnly) float CrankAngle = 0;
    UPROPERTY(BlueprintReadOnly) float Lean = 0;
    UPROPERTY(BlueprintReadOnly) bool bBraking = false;
    UPROPERTY(BlueprintReadOnly) float GradePct = 0;
    UPROPERTY(BlueprintReadOnly) FRidePrepWind Wind;
    UPROPERTY(BlueprintReadOnly) FRidePrepWeather Weather;
    UPROPERTY(BlueprintReadOnly) float SunElevationDeg = 30;
    UPROPERTY(BlueprintReadOnly) float SunAzimuthDeg = 180;
    UPROPERTY(BlueprintReadOnly) FRidePrepHud Hud;
    UPROPERTY(BlueprintReadOnly) bool bPaused = false;
    UPROPERTY(BlueprintReadOnly) bool bFinished = false;
    /** Local receive time (seconds, FPlatformTime) for interpolation. */
    double ReceivedAt = 0;
};

UENUM(BlueprintType)
enum class ERidePrepCamera : uint8 { Chase, FirstPerson, Side, Drone, Flyover, Cockpit };

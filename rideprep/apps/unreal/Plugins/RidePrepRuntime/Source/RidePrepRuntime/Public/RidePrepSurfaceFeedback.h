#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "Chaos/ChaosEngineInterface.h"
#include "RidePrepSurfaceFeedback.generated.h"

class UAudioComponent;
class USoundBase;

/** How a surface feels at 10 m/s (scaled with speed). */
USTRUCT(BlueprintType)
struct FRidePrepSurfaceFeel
{
    GENERATED_BODY()
    /** Vibration amplitude (cm) of the bike/camera. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RidePrep") float VibrationCm = 0.04f;
    /** Dominant vibration frequency (Hz). */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RidePrep") float VibrationHz = 24.f;
    /** Rolling-noise volume and pitch. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RidePrep") float RollVolume = 0.35f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RidePrep") float RollPitch = 1.f;
    /** Dust spawn rate (particles/s) — "SpawnRate" user parameter of the dust FX. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RidePrep") float Dust = 0.f;
};

/**
 * Surface feedback from Physical Materials: traces under both wheels (complex collision, so the hero road's potholes
 * and the gravel shoulder are what the tyres touch), reads the surface type (Config/DefaultEngine.ini: 1 Asphalt,
 * 2 Setts, 3 Gravel, 4 Grass, 5 Soil, 6 Water, 7 Metal) and drives vibration (with jolts from sudden height changes —
 * potholes, patch edges, crumbled edges), a looping rolling sound per surface, and dust on gravel and dirt. Speed comes
 * from the physics model; this is presentation only.
 */
UCLASS(ClassGroup = (RidePrep), meta = (BlueprintSpawnableComponent))
class RIDEPREPRUNTIME_API URidePrepSurfaceFeedback : public UActorComponent
{
    GENERATED_BODY()
public:
    URidePrepSurfaceFeedback();

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RidePrep") TMap<TEnumAsByte<EPhysicalSurface>, FRidePrepSurfaceFeel> Feel;
    /** Looping rolling sounds per surface (optional). */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RidePrep") TMap<TEnumAsByte<EPhysicalSurface>, TObjectPtr<USoundBase>> RollingSounds;
    /** Tag of an FX component on the owner (e.g. a Niagara dust system with a float user parameter "SpawnRate"). */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RidePrep") FName DustComponentTag = TEXT("Dust");
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "RidePrep") float TraceHalfHeightCm = 60.f;

    UPROPERTY(BlueprintReadOnly, Category = "RidePrep") TEnumAsByte<EPhysicalSurface> Surface = SurfaceType_Default;
    /** Offset to add to the camera (cockpit) or bike: buzz plus jolts. */
    UPROPERTY(BlueprintReadOnly, Category = "RidePrep") FVector VibrationOffsetCm = FVector::ZeroVector;
    /** 0..1: how rough the ride is right now (HUD, haptics). */
    UPROPERTY(BlueprintReadOnly, Category = "RidePrep") float Roughness = 0.f;

    /** Sample the ground at the wheel contact points (world) at speed (m/s); call once per frame. */
    UFUNCTION(BlueprintCallable, Category = "RidePrep") void Sample(const FVector& FrontContact, const FVector& RearContact, float SpeedMs, float DeltaSeconds);

private:
    bool Trace(const FVector& At, FHitResult& Hit) const;
    void UpdateAudio(const FRidePrepSurfaceFeel& F, float SpeedMs);
    UPROPERTY() TObjectPtr<UAudioComponent> Audio;
    float Phase = 0.f;
    float Jolt = 0.f;
    double LastFrontZ = 0.0;
    double FilteredFrontZ = 0.0;
    bool bHaveZ = false;
};

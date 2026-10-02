#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Pawn.h"
#include "RidePrepTypes.h"
#include "RidePrepRider.generated.h"

class USpringArmComponent;
class UCameraComponent;
class USkeletalMeshComponent;
class UAnimSequenceBase;
class URidePrepSurfaceFeedback;

/**
 * The rider placed on the route by s. Without a mesh assigned in the Blueprint it loads the rigged rider + bike
 * imported by Scripts/import_game_level.py (/Game/RidePrep/Rider/<bike>: tools/rider, MakeHuman CC0 body) and plays its
 * baked clips by crank angle — pedal (or pedal_drops), stand on steep slow climbs, coast — so the legs match the real
 * cadence; the whole model leans into corners. An AnimBP can still read CrankAngle, Lean, Standing and Tuck instead.
 * Surface feedback (PhysMat under the wheels) shakes the cockpit camera and the bike. Cameras: chase, first-person,
 * side, drone, flyover.
 */
UCLASS()
class RIDEPREPRUNTIME_API ARidePrepRider : public APawn
{
    GENERATED_BODY()
public:
    ARidePrepRider();
    virtual void BeginPlay() override;
    /** Place and pose: Location on the road surface (lane offset applied), YawDeg incl. the lane yaw, ExtraLeanRad from
     *  lane changes (+ = right). */
    void ApplyState(const FRidePrepStreamState& S, const FVector& Location, float YawDeg, float DeltaSeconds, float ExtraLeanRad = 0.f);
    UFUNCTION(BlueprintCallable) void SetCameraMode(ERidePrepCamera Mode);

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly) TObjectPtr<USkeletalMeshComponent> Mesh;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly) TObjectPtr<USpringArmComponent> Arm;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly) TObjectPtr<UCameraComponent> Camera;
    /** Cockpit: handlebars/hands mesh and a bike-computer widget attached to the camera (assign in the rider BP). */
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly) TObjectPtr<class UStaticMeshComponent> Cockpit;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly) TObjectPtr<class UWidgetComponent> BikeComputer;
    UPROPERTY(BlueprintReadOnly) float CrankAngle = 0;
    UPROPERTY(BlueprintReadOnly) float LeanDeg = 0;
    UPROPERTY(BlueprintReadOnly) float Standing = 0;
    UPROPERTY(BlueprintReadOnly) float Tuck = 0;
    UPROPERTY(BlueprintReadOnly) float WheelSpinDeg = 0;
    UPROPERTY(BlueprintReadOnly) ERidePrepCamera CameraMode = ERidePrepCamera::Chase;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly) TObjectPtr<URidePrepSurfaceFeedback> Surface;

    /** Where the imported rider lives, which bike, and the hands' position on a road bike ("hoods" or "drops"). */
    UPROPERTY(EditAnywhere, Category = "RidePrep|Rider") FString RiderAssetRoot = TEXT("/Game/RidePrep/Rider");
    UPROPERTY(EditAnywhere, Category = "RidePrep|Rider") FName Bike = TEXT("road");
    UPROPERTY(EditAnywhere, Category = "RidePrep|Rider") FName HandPosition = TEXT("hoods");
private:
    void LoadRiderAssets();
    void FaceForward();
    UAnimSequenceBase* Clip(const TCHAR* Name) const;
    UPROPERTY() TMap<FName, TObjectPtr<UAnimSequenceBase>> Clips;
    UPROPERTY() TObjectPtr<UAnimSequenceBase> CurrentClip;
    float BobPhase = 0;
    float Coasting = 0;
};

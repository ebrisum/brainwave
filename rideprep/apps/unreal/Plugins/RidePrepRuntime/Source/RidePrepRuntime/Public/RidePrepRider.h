#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Pawn.h"
#include "RidePrepTypes.h"
#include "RidePrepRider.generated.h"

class USpringArmComponent;
class UCameraComponent;
class USkeletalMeshComponent;

/**
 * The rider placed on the route by s. The AnimBP reads CrankAngle (Control Rig pedal IK), Lean, Standing and Tuck,
 * so the legs match the real cadence. Cameras: chase, first-person, side, drone.
 */
UCLASS()
class RIDEPREPRUNTIME_API ARidePrepRider : public APawn
{
    GENERATED_BODY()
public:
    ARidePrepRider();
    void ApplyState(const FRidePrepStreamState& S, const FVector& Location, float YawDeg, float DeltaSeconds);
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
private:
    float BobPhase = 0;
};

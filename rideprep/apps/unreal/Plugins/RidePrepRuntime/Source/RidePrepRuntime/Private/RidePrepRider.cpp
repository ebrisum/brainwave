#include "RidePrepRider.h"

#include "Camera/CameraComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "GameFramework/SpringArmComponent.h"

ARidePrepRider::ARidePrepRider()
{
    PrimaryActorTick.bCanEverTick = false;
    Mesh = CreateDefaultSubobject<USkeletalMeshComponent>(TEXT("Mesh"));
    RootComponent = Mesh;
    Arm = CreateDefaultSubobject<USpringArmComponent>(TEXT("Arm"));
    Arm->SetupAttachment(Mesh);
    Arm->TargetArmLength = 550.f;
    Arm->SocketOffset = FVector(0, 0, 230.f);
    Arm->bEnableCameraLag = true;
    Arm->CameraLagSpeed = 4.f;
    Arm->bEnableCameraRotationLag = true;
    Arm->CameraRotationLagSpeed = 4.f;
    Arm->bDoCollisionTest = true;
    Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
    Camera->SetupAttachment(Arm);
}

void ARidePrepRider::SetCameraMode(ERidePrepCamera Mode)
{
    CameraMode = Mode;
    switch (Mode)
    {
        case ERidePrepCamera::FirstPerson: Arm->TargetArmLength = 0; Arm->SocketOffset = FVector(10, 0, 155); Arm->SetRelativeRotation(FRotator::ZeroRotator); break;
        case ERidePrepCamera::Side: Arm->TargetArmLength = 500; Arm->SocketOffset = FVector(0, 0, 130); Arm->SetRelativeRotation(FRotator(0, 90, 0)); break;
        case ERidePrepCamera::Drone: Arm->TargetArmLength = 4000; Arm->SocketOffset = FVector(0, 0, 2800); Arm->SetRelativeRotation(FRotator(-30, 0, 0)); break;
        case ERidePrepCamera::Flyover: Arm->TargetArmLength = 7000; Arm->SocketOffset = FVector(0, 2500, 4500); Arm->SetRelativeRotation(FRotator(-25, 20, 0)); break;
        default: Arm->TargetArmLength = 550; Arm->SocketOffset = FVector(0, 0, 230); Arm->SetRelativeRotation(FRotator::ZeroRotator);
    }
}

void ARidePrepRider::ApplyState(const FRidePrepStreamState& S, const FVector& Location, float YawDeg, float Dt)
{
    LeanDeg = FMath::RadiansToDegrees(S.Lean);
    SetActorLocationAndRotation(Location, FRotator(0, YawDeg, -LeanDeg));
    CrankAngle = S.CrankAngle;
    WheelSpinDeg = FMath::Fmod(WheelSpinDeg + FMath::RadiansToDegrees(S.Speed / 0.335f) * Dt, 360.f);
    const float WantStand = (S.GradePct > 8.f && S.Cadence > 0.f && S.Cadence < 70.f) ? 1.f : 0.f;
    const float WantTuck = (S.Speed > 50.f / 3.6f && S.Power < 5.f) ? 1.f : 0.f;
    Standing = FMath::FInterpTo(Standing, WantStand, Dt, 2.f);
    Tuck = FMath::FInterpTo(Tuck, WantTuck, Dt, 1.5f);
}

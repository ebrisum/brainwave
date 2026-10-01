#include "RidePrepRider.h"

#include "Camera/CameraComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/WidgetComponent.h"
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
    // Cockpit pieces ride with the camera: bars ~60 cm ahead, ~27 cm below eye level (pulled into the lower third)
    Cockpit = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Cockpit"));
    Cockpit->SetupAttachment(Camera);
    Cockpit->SetRelativeLocation(FVector(60, 0, -27));
    Cockpit->SetRelativeRotation(FRotator(-40, 0, 0));
    Cockpit->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Cockpit->SetVisibility(false);
    BikeComputer = CreateDefaultSubobject<UWidgetComponent>(TEXT("BikeComputer"));
    BikeComputer->SetupAttachment(Cockpit);
    BikeComputer->SetRelativeLocation(FVector(-7, 0, 3));
    BikeComputer->SetDrawSize(FVector2D(256, 176));
    BikeComputer->SetWorldScale3D(FVector(0.02f));
    BikeComputer->SetVisibility(false);
}

void ARidePrepRider::SetCameraMode(ERidePrepCamera Mode)
{
    CameraMode = Mode;
    switch (Mode)
    {
        case ERidePrepCamera::Cockpit:
            // Eyes over the bars; the rider body is hidden, the cockpit mesh and computer are shown
            Arm->TargetArmLength = 0; Arm->SocketOffset = FVector(5, 0, 148); Arm->SetRelativeRotation(FRotator(-6, 0, 0));
            Arm->bEnableCameraLag = false;
            break;
        case ERidePrepCamera::FirstPerson: Arm->TargetArmLength = 0; Arm->SocketOffset = FVector(10, 0, 155); Arm->SetRelativeRotation(FRotator::ZeroRotator); break;
        case ERidePrepCamera::Side: Arm->TargetArmLength = 500; Arm->SocketOffset = FVector(0, 0, 130); Arm->SetRelativeRotation(FRotator(0, 90, 0)); break;
        case ERidePrepCamera::Drone: Arm->TargetArmLength = 4000; Arm->SocketOffset = FVector(0, 0, 2800); Arm->SetRelativeRotation(FRotator(-30, 0, 0)); break;
        case ERidePrepCamera::Flyover: Arm->TargetArmLength = 7000; Arm->SocketOffset = FVector(0, 2500, 4500); Arm->SetRelativeRotation(FRotator(-25, 20, 0)); break;
        default: Arm->TargetArmLength = 550; Arm->SocketOffset = FVector(0, 0, 230); Arm->SetRelativeRotation(FRotator::ZeroRotator);
    }
    const bool bCockpit = Mode == ERidePrepCamera::Cockpit;
    if (Mode != ERidePrepCamera::Cockpit) Arm->bEnableCameraLag = true;
    Mesh->SetOwnerNoSee(bCockpit);
    Cockpit->SetVisibility(bCockpit);
    BikeComputer->SetVisibility(bCockpit);
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
    if (CameraMode == ERidePrepCamera::Cockpit)
    {
        // Pedalling bob (two per crank revolution, bigger out of the saddle) and a gentle roll into corners
        BobPhase += S.Cadence / 60.f * 2.f * PI * Dt * 2.f;
        const float Amp = Standing > 0.5f ? 2.5f : 0.6f;
        Arm->SocketOffset = FVector(5, FMath::Sin(BobPhase / 2) * Amp * (Standing > 0.5f ? 1.6f : 0.5f), 148 + FMath::Abs(FMath::Sin(BobPhase / 2)) * Amp);
        Camera->SetRelativeRotation(FRotator(0, 0, LeanDeg * 0.6f));
    }
}

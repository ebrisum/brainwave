#include "RidePrepRider.h"

#include "Animation/AnimSequenceBase.h"
#include "AnimationRuntime.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Camera/CameraComponent.h"
#include "Components/SceneComponent.h"
#include "Engine/SkeletalMesh.h"
#include "RidePrepSurfaceFeedback.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/WidgetComponent.h"
#include "GameFramework/SpringArmComponent.h"

ARidePrepRider::ARidePrepRider()
{
    PrimaryActorTick.bCanEverTick = false;
    // Root at the tyre contact on the road (leaning pivots there); the mesh hangs below it so it can be turned to
    // face the road and shaken by the surface without moving the actor
    RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
    Mesh = CreateDefaultSubobject<USkeletalMeshComponent>(TEXT("Mesh"));
    Mesh->SetupAttachment(RootComponent);
    Arm = CreateDefaultSubobject<USpringArmComponent>(TEXT("Arm"));
    Arm->SetupAttachment(RootComponent);
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
    Surface = CreateDefaultSubobject<URidePrepSurfaceFeedback>(TEXT("Surface"));
}

void ARidePrepRider::BeginPlay()
{
    Super::BeginPlay();
    if (!Mesh->GetSkeletalMeshAsset()) LoadRiderAssets();
}

void ARidePrepRider::LoadRiderAssets()
{
    // Find the imported rider by folder (Interchange names vary: rider_road, SK_rider_road, …; clips keep the glTF
    // animation names somewhere in theirs)
    IAssetRegistry& AR = FModuleManager::LoadModuleChecked<FAssetRegistryModule>(TEXT("AssetRegistry")).Get();
    TArray<FAssetData> Found;
    AR.GetAssetsByPath(FName(*(RiderAssetRoot / Bike.ToString())), Found, true);
    USkeletalMesh* SkMesh = nullptr;
    for (const FAssetData& A : Found)
    {
        UObject* Obj = A.GetAsset();
        if (USkeletalMesh* SM = Cast<USkeletalMesh>(Obj)) SkMesh = SM;
        else if (UAnimSequenceBase* Seq = Cast<UAnimSequenceBase>(Obj))
        {
            const FString N = A.AssetName.ToString();
            // most specific first: "pedal_drops_rolling" must not be taken for "pedal"
            for (const TCHAR* K : { TEXT("pedal_drops_rolling"), TEXT("coast_drops_rolling"), TEXT("pedal_rolling"), TEXT("stand_rolling"),
                                    TEXT("coast_rolling"), TEXT("pedal_drops"), TEXT("coast_drops"), TEXT("pedal"), TEXT("stand"), TEXT("coast") })
                if (N.EndsWith(K) || N.Contains(FString(TEXT("_")) + K + TEXT("_")))
                {
                    if (!Clips.Contains(K)) Clips.Add(K, Seq);
                    break;
                }
        }
    }
    if (!SkMesh)
    {
        UE_LOG(LogTemp, Warning, TEXT("RidePrep: no rider under %s/%s (run Scripts/import_game_level.py)"), *RiderAssetRoot, *Bike.ToString());
        return;
    }
    Mesh->SetSkeletalMeshAsset(SkMesh);
    Mesh->SetAnimationMode(EAnimationMode::AnimationSingleNode);
    FaceForward();
    UE_LOG(LogTemp, Log, TEXT("RidePrep: rider %s with %d clips"), *SkMesh->GetName(), Clips.Num());
}

void ARidePrepRider::FaceForward()
{
    // The model faces along its bike (rear → front axle); turn the mesh so that is the actor's +X, whatever axis
    // conversion the importer applied. Reference pose, so it works before the first animation update.
    const USkeletalMesh* SkMesh = Mesh->GetSkeletalMeshAsset();
    if (!SkMesh) return;
    const FReferenceSkeleton& Ref = SkMesh->GetRefSkeleton();
    auto Bone = [&Ref](const TCHAR* A, const TCHAR* B) {
        int32 I = Ref.FindBoneIndex(FName(A));
        if (I == INDEX_NONE) I = Ref.FindBoneIndex(FName(B));
        return I == INDEX_NONE ? FVector::ZeroVector : FAnimationRuntime::GetComponentSpaceTransformRefPose(Ref, I).GetLocation();
    };
    const FVector Fwd = Bone(TEXT("wheel.F"), TEXT("wheel_F")) - Bone(TEXT("wheel.R"), TEXT("wheel_R"));
    if (Fwd.Size2D() > 10.f)
        Mesh->SetRelativeRotation(FRotator(0, -FMath::RadiansToDegrees(FMath::Atan2(Fwd.Y, Fwd.X)), 0));
}

UAnimSequenceBase* ARidePrepRider::Clip(const TCHAR* Name) const
{
    // The *_rolling clips also turn the wheels (whole turns per crank turn), so prefer them
    if (const TObjectPtr<UAnimSequenceBase>* R = Clips.Find(FName(*(FString(Name) + TEXT("_rolling")))))
        return R->Get();
    const TObjectPtr<UAnimSequenceBase>* C = Clips.Find(Name);
    return C ? C->Get() : nullptr;
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

void ARidePrepRider::ApplyState(const FRidePrepStreamState& S, const FVector& Location, float YawDeg, float Dt, float ExtraLeanRad)
{
    LeanDeg = FMath::RadiansToDegrees(S.Lean + ExtraLeanRad);
    SetActorLocationAndRotation(Location, FRotator(0, YawDeg, -LeanDeg));
    CrankAngle = S.CrankAngle;
    WheelSpinDeg = FMath::Fmod(WheelSpinDeg + FMath::RadiansToDegrees(S.Speed / 0.335f) * Dt, 360.f);
    const float WantStand = (S.GradePct > 8.f && S.Cadence > 0.f && S.Cadence < 70.f) ? 1.f : 0.f;
    const float WantTuck = (S.Speed > 50.f / 3.6f && S.Power < 5.f) ? 1.f : 0.f;
    Standing = FMath::FInterpTo(Standing, WantStand, Dt, 2.f);
    Tuck = FMath::FInterpTo(Tuck, WantTuck, Dt, 1.5f);
    Coasting = FMath::FInterpTo(Coasting, (S.Cadence < 8.f || S.Power < 5.f) ? 1.f : 0.f, Dt, 3.f);
    // Baked clips (no AnimBP): one revolution per clip, clip time from the crank angle (clips start with the right
    // crank forward); the dominant state picks the clip
    if (Clips.Num() && Mesh->GetAnimationMode() == EAnimationMode::AnimationSingleNode)
    {
        const bool bDrops = HandPosition == TEXT("drops");
        UAnimSequenceBase* Want = Coasting > 0.5f ? (bDrops && Clip(TEXT("coast_drops")) ? Clip(TEXT("coast_drops")) : Clip(TEXT("coast")))
                                : Standing > 0.5f ? Clip(TEXT("stand"))
                                : (bDrops && Clip(TEXT("pedal_drops")) ? Clip(TEXT("pedal_drops")) : Clip(TEXT("pedal")));
        if (Want && Want != CurrentClip)
        {
            Mesh->PlayAnimation(Want, false);
            Mesh->SetPlayRate(0.f);
            CurrentClip = Want;
        }
        if (CurrentClip)
        {
            const float Phi = FMath::Fmod(FMath::Fmod(S.CrankAngle - PI / 2, 2 * PI) + 2 * PI, 2 * PI);
            Mesh->SetPosition(Phi / (2 * PI) * CurrentClip->GetPlayLength(), false);
        }
    }
    // Surface under the wheels (contact points ~0.6 m ahead of / 0.4 m behind the bottom bracket)
    const FVector Fwd = GetActorForwardVector();
    Surface->Sample(Location + Fwd * 60.f, Location - Fwd * 40.f, S.Speed, Dt);
    Mesh->SetRelativeLocation(FVector(0, 0, Surface->VibrationOffsetCm.Z * 0.3f));
    if (CameraMode == ERidePrepCamera::Cockpit)
    {
        // Pedalling bob (two per crank revolution, bigger out of the saddle) and a gentle roll into corners
        BobPhase += S.Cadence / 60.f * 2.f * PI * Dt * 2.f;
        const float Amp = Standing > 0.5f ? 2.5f : 0.6f;
        Arm->SocketOffset = FVector(5, FMath::Sin(BobPhase / 2) * Amp * (Standing > 0.5f ? 1.6f : 0.5f), 148 + FMath::Abs(FMath::Sin(BobPhase / 2)) * Amp);
        Camera->SetRelativeRotation(FRotator(0, 0, LeanDeg * 0.6f));
        Camera->SetRelativeLocation(Surface->VibrationOffsetCm);
    }
}

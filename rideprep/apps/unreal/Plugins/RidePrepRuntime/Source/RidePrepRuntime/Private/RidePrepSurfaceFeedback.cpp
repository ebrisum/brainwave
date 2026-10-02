#include "RidePrepSurfaceFeedback.h"

#include "Components/AudioComponent.h"
#include "Engine/World.h"
#include "GameFramework/Actor.h"
#include "Particles/ParticleSystemComponent.h"
#include "PhysicalMaterials/PhysicalMaterial.h"
#include "Sound/SoundBase.h"

URidePrepSurfaceFeedback::URidePrepSurfaceFeedback()
{
    PrimaryComponentTick.bCanEverTick = false;
    auto Add = [this](EPhysicalSurface S, float Cm, float Hz, float Vol, float Pitch, float Dust) {
        FRidePrepSurfaceFeel F;
        F.VibrationCm = Cm; F.VibrationHz = Hz; F.RollVolume = Vol; F.RollPitch = Pitch; F.Dust = Dust;
        Feel.Add(S, F);
    };
    Add(SurfaceType_Default, 0.04f, 24.f, 0.30f, 1.00f, 0.f);
    Add(SurfaceType1, 0.04f, 24.f, 0.30f, 1.00f, 0.f);    // Asphalt
    Add(SurfaceType2, 0.30f, 16.f, 0.65f, 0.80f, 0.f);    // Setts (porphyry): strong rumble
    Add(SurfaceType3, 0.20f, 30.f, 0.70f, 1.15f, 40.f);   // Gravel: crunch and dust
    Add(SurfaceType4, 0.12f, 12.f, 0.25f, 0.70f, 0.f);    // Grass
    Add(SurfaceType5, 0.16f, 14.f, 0.40f, 0.85f, 25.f);   // Soil / dirt
    Add(SurfaceType6, 0.02f, 8.f, 0.50f, 0.60f, 0.f);     // Water (splash sound)
    Add(SurfaceType7, 0.10f, 40.f, 0.45f, 1.30f, 0.f);    // Metal (bridge joints, grates)
}

bool URidePrepSurfaceFeedback::Trace(const FVector& At, FHitResult& Hit) const
{
    FCollisionQueryParams Q(SCENE_QUERY_STAT(RidePrepSurface), true, GetOwner());
    Q.bReturnPhysicalMaterial = true;
    const FVector Up(0, 0, TraceHalfHeightCm);
    return GetWorld()->LineTraceSingleByChannel(Hit, At + Up, At - Up, ECC_Visibility, Q);
}

void URidePrepSurfaceFeedback::Sample(const FVector& FrontContact, const FVector& RearContact, float SpeedMs, float Dt)
{
    if (!GetWorld() || Dt <= 0.f) return;
    FHitResult Front, Rear;
    const bool bFront = Trace(FrontContact, Front);
    const bool bRear = Trace(RearContact, Rear);
    const FHitResult& Main = bRear ? Rear : Front;
    if (bFront || bRear)
        Surface = UPhysicalMaterial::DetermineSurfaceType(Main.PhysMaterial.Get());
    const FRidePrepSurfaceFeel* F = Feel.Find(Surface);
    const FRidePrepSurfaceFeel Def;
    const FRidePrepSurfaceFeel& S = F ? *F : Def;
    // Jolts: the front wheel dropping into or climbing out of something faster than the road's own profile
    if (bFront)
    {
        const double Z = Front.ImpactPoint.Z;
        if (!bHaveZ) { LastFrontZ = FilteredFrontZ = Z; bHaveZ = true; }
        FilteredFrontZ += (Z - FilteredFrontZ) * FMath::Min(1.0, Dt * 6.0);
        const double Step = FMath::Abs(Z - FilteredFrontZ);
        Jolt = FMath::Max(Jolt * FMath::Exp(-Dt * 9.f), (float)FMath::Clamp(Step / 3.0, 0.0, 1.5));  // 3 cm step = full jolt
        LastFrontZ = Z;
    }
    const float V = FMath::Max(0.f, SpeedMs);
    const float Scale = FMath::Pow(FMath::Clamp(V / 10.f, 0.f, 2.f), 0.7f);
    Phase += 2.f * PI * S.VibrationHz * Dt * (0.5f + 0.5f * FMath::Clamp(V / 10.f, 0.f, 2.f));
    const float Amp = S.VibrationCm * Scale + Jolt * 0.8f;
    VibrationOffsetCm = FVector(0.3f * FMath::Sin(Phase * 0.61f + 1.3f), 0.5f * FMath::Sin(Phase * 1.37f + 0.4f), FMath::Sin(Phase)) * Amp;
    Roughness = FMath::Clamp(S.VibrationCm * Scale / 0.3f + Jolt, 0.f, 1.f);
    UpdateAudio(S, V);
    if (AActor* Owner = GetOwner())
        if (UFXSystemComponent* Dust = Owner->FindComponentByTag<UFXSystemComponent>(DustComponentTag))
        {
            const float Rate = S.Dust * FMath::Clamp(V / 10.f, 0.f, 2.f);
            Dust->SetFloatParameter(TEXT("SpawnRate"), Rate);
            if (Rate > 0.5f && !Dust->IsActive()) Dust->Activate();
            else if (Rate <= 0.5f && Dust->IsActive()) Dust->Deactivate();
        }
}

void URidePrepSurfaceFeedback::UpdateAudio(const FRidePrepSurfaceFeel& F, float V)
{
    TObjectPtr<USoundBase>* Snd = RollingSounds.Find(Surface);
    if (!Snd || !*Snd)
    {
        if (Audio && Audio->IsPlaying()) Audio->FadeOut(0.3f, 0.f);
        return;
    }
    if (!Audio)
    {
        AActor* Owner = GetOwner();
        if (!Owner || !Owner->GetRootComponent()) return;
        Audio = NewObject<UAudioComponent>(Owner);
        Audio->SetupAttachment(Owner->GetRootComponent());
        Audio->bAutoActivate = false;
        Audio->RegisterComponent();
    }
    if (Audio->Sound != *Snd)
    {
        Audio->SetSound(*Snd);
        Audio->FadeIn(0.25f, 1.f);
    }
    else if (!Audio->IsPlaying())
        Audio->Play();
    Audio->SetVolumeMultiplier(FMath::Max(0.001f, F.RollVolume * FMath::Clamp(V / 10.f, 0.f, 1.5f)));
    Audio->SetPitchMultiplier(F.RollPitch * (0.8f + 0.2f * FMath::Clamp(V / 10.f, 0.f, 2.f)));
}

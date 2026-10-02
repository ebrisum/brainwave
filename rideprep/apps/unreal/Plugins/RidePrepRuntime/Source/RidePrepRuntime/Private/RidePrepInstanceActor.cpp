#include "RidePrepInstanceActor.h"

#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Engine/StaticMesh.h"

ARidePrepInstanceActor::ARidePrepInstanceActor()
{
    PrimaryActorTick.bCanEverTick = false;
    RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
    RootComponent->SetMobility(EComponentMobility::Static);
}

int32 ARidePrepInstanceActor::AddInstances(FName Asset, UStaticMesh* Mesh, const TArray<FTransform>& Transforms, float CullStartCm, float CullEndCm,
                                           bool bCollision, bool bCastShadow)
{
    if (!Mesh || Transforms.IsEmpty()) return 0;
    TObjectPtr<UHierarchicalInstancedStaticMeshComponent>* Found = ByAsset.Find(Asset);
    UHierarchicalInstancedStaticMeshComponent* C = Found ? Found->Get() : nullptr;
    if (!C)
    {
        C = NewObject<UHierarchicalInstancedStaticMeshComponent>(this, MakeUniqueObjectName(this, UHierarchicalInstancedStaticMeshComponent::StaticClass(),
                                                                                               FName(*FString::Printf(TEXT("HISM_%s"), *Asset.ToString()))),
                                                                RF_Transactional);
        C->SetMobility(EComponentMobility::Static);
        C->SetupAttachment(RootComponent);
        C->SetStaticMesh(Mesh);
        C->SetCollisionEnabled(bCollision ? ECollisionEnabled::QueryAndPhysics : ECollisionEnabled::NoCollision);
        C->SetCastShadow(bCastShadow);
        if (CullEndCm > 0.f) C->SetCullDistances((int32)CullStartCm, (int32)CullEndCm);
        AddInstanceComponent(C);  // saved with the actor in the editor
        C->RegisterComponent();
        ByAsset.Add(Asset, C);
    }
    C->AddInstances(Transforms, /*bShouldReturnIndices*/ false, /*bWorldSpace*/ false);
    return Transforms.Num();
}

void ARidePrepInstanceActor::ClearInstances()
{
    for (auto& [Name, C] : ByAsset)
    {
        if (C) C->DestroyComponent();
    }
    ByAsset.Reset();
}

int32 ARidePrepInstanceActor::NumInstances() const
{
    int32 N = 0;
    for (const auto& [Name, C] : ByAsset) N += C ? C->GetInstanceCount() : 0;
    return N;
}

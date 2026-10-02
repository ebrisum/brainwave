#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "RidePrepInstanceActor.generated.h"

class UHierarchicalInstancedStaticMeshComponent;
class UStaticMesh;

/**
 * One per game-art chunk: kit asset instances (trees, vines, props) as HISM components, so World Partition streams them
 * with the chunk. Filled by Scripts/import_game_level.py in the editor (components are saved with the level) or at
 * runtime. Transforms are actor-local (chunk origin), in Unreal units.
 */
UCLASS()
class RIDEPREPRUNTIME_API ARidePrepInstanceActor : public AActor
{
    GENERATED_BODY()
public:
    ARidePrepInstanceActor();

    /** Adds (or extends) the HISM for `Asset`. Collision only for solid props (guardrails, barriers, signs). */
    UFUNCTION(BlueprintCallable, Category = "RidePrep")
    int32 AddInstances(FName Asset, UStaticMesh* Mesh, const TArray<FTransform>& Transforms, float CullStartCm = 0.f, float CullEndCm = 0.f,
                       bool bCollision = false, bool bCastShadow = true);

    UFUNCTION(BlueprintCallable, Category = "RidePrep")
    void ClearInstances();

    UFUNCTION(BlueprintPure, Category = "RidePrep")
    int32 NumInstances() const;

private:
    UPROPERTY(VisibleAnywhere, Category = "RidePrep")
    TMap<FName, TObjectPtr<UHierarchicalInstancedStaticMeshComponent>> ByAsset;
};

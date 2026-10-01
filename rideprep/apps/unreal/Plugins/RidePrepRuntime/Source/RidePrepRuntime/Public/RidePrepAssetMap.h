#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "RidePrepAssetMap.generated.h"

class UStaticMesh;
class UMaterialInterface;
class UMaterialParameterCollection;

/**
 * Maps the package's engine-agnostic ids to this project's assets: vegetation species → (Nanite) meshes,
 * material catalogue ids → material instances. One asset per project; any course loads without per-course work.
 */
UCLASS(BlueprintType)
class RIDEPREPRUNTIME_API URidePrepAssetMap : public UPrimaryDataAsset
{
    GENERATED_BODY()
public:
    /** Key: "<category>" or "<category>_<species>", e.g. "tree_deciduous_2", "prop_0" (km post). */
    UPROPERTY(EditAnywhere, BlueprintReadOnly) TMap<FName, TSoftObjectPtr<UStaticMesh>> InstanceMeshes;
    /** Key: material id from materials.json (e.g. "road_sett"). */
    UPROPERTY(EditAnywhere, BlueprintReadOnly) TMap<FName, TSoftObjectPtr<UMaterialInterface>> Materials;
    /** Terrain material blending land-cover layers via vertex colour (quick-tier tiles) or weight maps (editor mode). */
    UPROPERTY(EditAnywhere, BlueprintReadOnly) TSoftObjectPtr<UMaterialInterface> TerrainMaterial;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) TSoftObjectPtr<UMaterialInterface> RoadMaterial;
    /** Parameters: WindDirX, WindDirY, WindStrength, Gust, Wetness, CloudCover. Drives foliage sway and wet surfaces. */
    UPROPERTY(EditAnywhere, BlueprintReadOnly) TSoftObjectPtr<UMaterialParameterCollection> EnvironmentParameters;
};

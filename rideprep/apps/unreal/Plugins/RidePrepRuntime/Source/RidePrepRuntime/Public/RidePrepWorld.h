#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "RidePrepTypes.h"
#include "RidePrepLaneKeeper.h"
#include "RidePrepWorld.generated.h"

class URidePrepCourse;
class URidePrepStreamClient;
class URidePrepAssetMap;
class UProceduralMeshComponent;
class UHierarchicalInstancedStaticMeshComponent;
class ARidePrepRider;
class ADirectionalLight;
class AExponentialHeightFog;

/**
 * Runtime course world: loads a package at BeginPlay (or when the ride core says hello), builds terrain tiles,
 * the road ribbon and HISM vegetation on background threads, streams baked glTF chunks 3 km ahead / 500 m behind,
 * and drives sun, fog and the wind parameter collection from the state stream.
 */
UCLASS()
class RIDEPREPRUNTIME_API ARidePrepWorld : public AActor
{
    GENERATED_BODY()
public:
    ARidePrepWorld();

    /** Package directory; empty = take it from the ride core's hello message. */
    UPROPERTY(EditAnywhere, Category = "RidePrep") FString PackageDir;
    UPROPERTY(EditAnywhere, Category = "RidePrep") FString RideCoreUrl = TEXT("ws://127.0.0.1:8765");
    UPROPERTY(EditAnywhere, Category = "RidePrep") TObjectPtr<URidePrepAssetMap> Assets;
    UPROPERTY(EditAnywhere, Category = "RidePrep") TSubclassOf<ARidePrepRider> RiderClass;
    UPROPERTY(EditAnywhere, Category = "RidePrep") TObjectPtr<ADirectionalLight> Sun;
    UPROPERTY(EditAnywhere, Category = "RidePrep") TObjectPtr<AExponentialHeightFog> Fog;
    UPROPERTY(EditAnywhere, Category = "RidePrep|Streaming") float TerrainRadiusM = 5000;
    UPROPERTY(EditAnywhere, Category = "RidePrep|Streaming") float ChunkAheadM = 3000;
    UPROPERTY(EditAnywhere, Category = "RidePrep|Streaming") float ChunkBehindM = 500;
    UPROPERTY(EditAnywhere, Category = "RidePrep|Streaming") float VegetationRadiusM = 3000;
    /** Line on the road: keep right ~1 m from the edge (open roads) or the racing line (closed roads). */
    UPROPERTY(EditAnywhere, Category = "RidePrep|Rider") bool bRacingLine = false;

    /**
     * Real-world view: Google Photorealistic 3D Tiles (what Google Earth shows) streamed through Cesium for Unreal,
     * anchored to the course frame at the rider and height-calibrated by line traces at the road. Our generated terrain,
     * buildings, vegetation and chunks are hidden; the road ribbon, markers and rider stay. Runtime streaming only.
     * The key can also come from the command line: -GoogleTilesKey=... (never commit it).
     */
    UPROPERTY(EditAnywhere, Category = "RidePrep|Photoreal") bool bPhotoreal = false;
    UPROPERTY(EditAnywhere, Category = "RidePrep|Photoreal") FString GoogleApiKey;
    /** Any 3D Tiles URL instead of Google (e.g. a package's devtiles/tileset.json for testing without a key). */
    UPROPERTY(EditAnywhere, Category = "RidePrep|Photoreal") FString TilesetUrlOverride;
    UPROPERTY(EditAnywhere, Category = "RidePrep|Photoreal") float ReanchorDistanceM = 750;

    UPROPERTY(BlueprintReadOnly) TObjectPtr<URidePrepCourse> Course;
    UPROPERTY(BlueprintReadOnly) TObjectPtr<URidePrepStreamClient> Stream;
    UPROPERTY(BlueprintReadOnly) TObjectPtr<ARidePrepRider> Rider;

    UFUNCTION(BlueprintCallable) bool LoadCourse(const FString& Dir);

    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
    virtual void Tick(float DeltaSeconds) override;

private:
    UFUNCTION() void HandleHello(const FString& CourseId, const FString& PackagePath);
    void BuildRoad();
    void UpdateTerrain(const FVector2D& Enu);
    void UpdateVegetation(const FVector2D& Enu);
    void UpdateChunks(double S);
    void UpdateEnvironment(const FRidePrepStreamState& S);
    UMaterialInterface* Material(FName Id) const;
    void SetupPhotoreal();
    void UpdatePhotoreal(double S);
    void ApplyStyle();
    TMap<FName, FLinearColor> StyleColors;
    UPROPERTY() TObjectPtr<AActor> Tileset;
    UPROPERTY() TObjectPtr<AActor> Georeference;
    double AnchorS = -1e9;
    double VerticalOffsetCm = 0;
    bool bHeightCalibrated = false;
    double LastCalibration = 0;

    UPROPERTY() TMap<FIntPoint, TObjectPtr<UProceduralMeshComponent>> TerrainTiles;
    TSet<FIntPoint> TerrainLoading;
    UPROPERTY() TArray<TObjectPtr<UProceduralMeshComponent>> RoadSections;
    UPROPERTY() TMap<FName, TObjectPtr<UHierarchicalInstancedStaticMeshComponent>> Foliage;
    TMap<FIntPoint, TArray<int32>> InstanceCells;
    TSet<FIntPoint> FoliageCellsLoaded;
    UPROPERTY() TMap<int32, TObjectPtr<AActor>> LoadedChunks;
    /** Presentation physics: where the bike rides across the road (RidePrepLaneKeeper.h, same as the web client). */
    TUniquePtr<RidePrep::LaneKeeper> Lane;
    double LastLaneS = -1e9;
    FVector RiderOnRoad(double S, double OffsetM) const;
    TSet<int32> ChunksLoading;
    double LastStreamS = -1e9;
};

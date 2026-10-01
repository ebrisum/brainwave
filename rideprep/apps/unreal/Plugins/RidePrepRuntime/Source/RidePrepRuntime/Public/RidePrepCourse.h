#pragma once

#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "RidePrepCourseMath.h"
#include "RidePrepCourse.generated.h"

/** One quick-tier terrain tile decoded on a worker thread. */
struct FRidePrepTerrainTile
{
    int32 I = 0, J = 0, N = 0;
    TArray<float> Heights;     // N×N, row 0 = north edge
    TArray<uint8> LandCover;   // N×N WorldCover classes
};

struct FRidePrepInstance
{
    FVector3f Enu;
    float Rot = 0, Scale = 1, Height = 1;
    uint8 Category = 0, Species = 0;
};

/**
 * A gpx2course package loaded from a local directory: manifest, route.bin, instances.bin and terrain tiles.
 * Everything else (weather, wind layers) stays in the ride core; Unreal is a view of the ride.
 */
UCLASS(BlueprintType)
class RIDEPREPRUNTIME_API URidePrepCourse : public UObject
{
    GENERATED_BODY()
public:
    /** Loads manifest.json, route.bin and instances.bin. Returns false with an error message on failure. */
    bool LoadFromDirectory(const FString& Dir, FString& OutError);

    /** Decode one terrain tile (thread-safe; call from a worker). */
    bool LoadTerrainTile(int32 I, int32 J, FRidePrepTerrainTile& Out) const;

    UFUNCTION(BlueprintCallable) FVector PositionAtS(double S) const;   // Unreal cm
    UFUNCTION(BlueprintCallable) float YawAtS(double S) const;           // Unreal yaw (deg)
    UFUNCTION(BlueprintPure) FString GetCourseName() const { return Name; }
    UFUNCTION(BlueprintPure) double GetDistanceM() const { return DistanceM; }

    FString Dir;
    FString Name;
    FString CourseId;
    double DistanceM = 0;
    double OriginLat = 0, OriginLon = 0, OriginH = 0;
    RidePrep::RouteArrays Route;
    TArray<FRidePrepInstance> Instances;
    TArray<FString> InstanceCategories;
    TArray<FIntPoint> TerrainTiles;
    double TileSizeM = 3000, VertexSpacingM = 10;
    struct FChunk { int32 Id; double SStart, SEnd; FVector OriginEnu; TArray<FString> Lods; bool bBaked; };
    TArray<FChunk> Chunks;
    TSharedPtr<class FJsonObject> Manifest;
};

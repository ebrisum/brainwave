#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "RidePrepRoadSpline.generated.h"

class USplineComponent;

/**
 * The course road as a spline (one per chunk, placed by Scripts/import_game_level.py), tagged "RidePrepRoad" so PCG
 * graphs can find it: exclusion zones around the carriageway, sampling along the edge (shoulder detail, verge flowers).
 */
UCLASS()
class RIDEPREPRUNTIME_API ARidePrepRoadSpline : public AActor
{
    GENERATED_BODY()
public:
    ARidePrepRoadSpline();

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "RidePrep") TObjectPtr<USplineComponent> Spline;

    /** Replace the spline with these points (actor-local cm, along the direction of travel). */
    UFUNCTION(BlueprintCallable, Category = "RidePrep") void SetPoints(const TArray<FVector>& Points);
};

#include "RidePrepRoadSpline.h"

#include "Components/SplineComponent.h"

ARidePrepRoadSpline::ARidePrepRoadSpline()
{
    PrimaryActorTick.bCanEverTick = false;
    Spline = CreateDefaultSubobject<USplineComponent>(TEXT("Spline"));
    RootComponent = Spline;
    Spline->SetMobility(EComponentMobility::Static);
    Tags.Add(TEXT("RidePrepRoad"));
}

void ARidePrepRoadSpline::SetPoints(const TArray<FVector>& Points)
{
    Spline->SetSplinePoints(Points, ESplineCoordinateSpace::Local, true);
}

#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "RidePrepTypes.h"
#include "RidePrepHudWidget.generated.h"

/** UMG HUD base: bind text blocks to State (same layout as the web HUD, spec §11). */
UCLASS(Abstract)
class RIDEPREPRUNTIME_API URidePrepHudWidget : public UUserWidget
{
    GENERATED_BODY()
public:
    UPROPERTY(BlueprintReadOnly, Category = "RidePrep") FRidePrepStreamState State;
    UFUNCTION(BlueprintImplementableEvent, Category = "RidePrep") void OnStateUpdated();
    UFUNCTION(BlueprintPure, Category = "RidePrep") FText FormatDuration(float Seconds) const;
    UFUNCTION(BlueprintPure, Category = "RidePrep") FText CompassName(float Degrees) const;
};

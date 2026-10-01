#include "RidePrepHudWidget.h"

FText URidePrepHudWidget::FormatDuration(float Seconds) const
{
    const int32 S = FMath::Max(0, FMath::FloorToInt(Seconds));
    return S >= 3600 ? FText::FromString(FString::Printf(TEXT("%d:%02d:%02d"), S / 3600, (S / 60) % 60, S % 60))
                     : FText::FromString(FString::Printf(TEXT("%d:%02d"), S / 60, S % 60));
}

FText URidePrepHudWidget::CompassName(float Degrees) const
{
    static const TCHAR* Dirs[] = { TEXT("N"), TEXT("NNE"), TEXT("NE"), TEXT("ENE"), TEXT("E"), TEXT("ESE"), TEXT("SE"), TEXT("SSE"),
                                   TEXT("S"), TEXT("SSW"), TEXT("SW"), TEXT("WSW"), TEXT("W"), TEXT("WNW"), TEXT("NW"), TEXT("NNW") };
    const int32 I = FMath::RoundToInt(FMath::Fmod(FMath::Fmod(Degrees, 360.f) + 360.f, 360.f) / 22.5f) % 16;
    return FText::FromString(Dirs[I]);
}

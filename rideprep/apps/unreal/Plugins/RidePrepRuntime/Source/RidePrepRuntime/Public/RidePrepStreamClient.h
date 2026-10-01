#pragma once

#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "RidePrepTypes.h"
#include "RidePrepStreamClient.generated.h"

class IWebSocket;

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnRidePrepHello, const FString&, CourseId, const FString&, PackagePath);

/** WebSocket client for the ride core (ws://127.0.0.1:8765, MessagePack, 50 Hz). Keeps the last two states for interpolation. */
UCLASS(BlueprintType)
class RIDEPREPRUNTIME_API URidePrepStreamClient : public UObject
{
    GENERATED_BODY()
public:
    UFUNCTION(BlueprintCallable) void Connect(const FString& Url = TEXT("ws://127.0.0.1:8765"));
    UFUNCTION(BlueprintCallable) void Disconnect();
    UFUNCTION(BlueprintCallable) void SendPause(bool bPause);
    UFUNCTION(BlueprintCallable) void SendCamera(ERidePrepCamera Mode);
    UFUNCTION(BlueprintCallable) void SendDifficulty(float Value);
    UFUNCTION(BlueprintCallable) void SendEnd();
    UFUNCTION(BlueprintPure) bool IsConnected() const;

    /** Interpolated route distance at the current time (renderer runs faster than 50 Hz). */
    double InterpolatedS(double Now) const;

    UPROPERTY(BlueprintReadOnly) FRidePrepStreamState Latest;
    FRidePrepStreamState Previous;
    UPROPERTY(BlueprintAssignable) FOnRidePrepHello OnHello;

private:
    TSharedPtr<IWebSocket> Socket;
    void OnRaw(const void* Data, SIZE_T Size, SIZE_T Remaining);
    TArray<uint8> Partial;
    void Send(const std::vector<uint8_t>& Bytes);
};

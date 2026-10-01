#include "RidePrepWorld.h"

#include "Async/Async.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Components/DirectionalLightComponent.h"
#include "Components/ExponentialHeightFogComponent.h"
#include "Engine/DirectionalLight.h"
#include "Engine/ExponentialHeightFog.h"
#include "Engine/StaticMesh.h"
#include "Kismet/KismetMaterialLibrary.h"
#include "Materials/MaterialParameterCollection.h"
#include "Misc/Paths.h"
#include "ProceduralMeshComponent.h"
#include "RidePrepAssetMap.h"
#include "RidePrepCourse.h"
#include "RidePrepRider.h"
#include "RidePrepStreamClient.h"
#if WITH_GLTFRUNTIME
#include "glTFRuntimeAssetActor.h"
#include "glTFRuntimeFunctionLibrary.h"
#endif
#if WITH_CESIUM
#include "CesiumGeoreference.h"
#include "Kismet/GameplayStatics.h"
#endif

static constexpr double CellM = 1500.0;

// WorldCover class → terrain vertex colour (linear); the terrain material multiplies/blends by this.
static FLinearColor LandCoverColor(uint8 C)
{
    switch (C)
    {
        case 10: case 95: return FLinearColor(0.035f, 0.07f, 0.02f);
        case 40: return FLinearColor(0.26f, 0.26f, 0.06f);
        case 50: return FLinearColor(0.17f, 0.19f, 0.12f);
        case 60: case 70: return FLinearColor(0.26f, 0.21f, 0.15f);
        case 80: return FLinearColor(0.012f, 0.04f, 0.07f);
        default: return FLinearColor(0.09f, 0.2f, 0.04f);
    }
}

ARidePrepWorld::ARidePrepWorld()
{
    PrimaryActorTick.bCanEverTick = true;
    RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
}

void ARidePrepWorld::BeginPlay()
{
    Super::BeginPlay();
    Stream = NewObject<URidePrepStreamClient>(this);
    Stream->OnHello.AddDynamic(this, &ARidePrepWorld::HandleHello);
    Stream->Connect(RideCoreUrl);
    if (!PackageDir.IsEmpty()) LoadCourse(PackageDir);
}

void ARidePrepWorld::EndPlay(const EEndPlayReason::Type Reason)
{
    if (Stream) Stream->Disconnect();
    Super::EndPlay(Reason);
}

void ARidePrepWorld::HandleHello(const FString& CourseId, const FString& PackagePath)
{
    if (!Course && FPaths::DirectoryExists(PackagePath)) LoadCourse(PackagePath);
}

UMaterialInterface* ARidePrepWorld::Material(FName Id) const
{
    if (!Assets) return nullptr;
    if (const TSoftObjectPtr<UMaterialInterface>* M = Assets->Materials.Find(Id)) return M->LoadSynchronous();
    return nullptr;
}

bool ARidePrepWorld::LoadCourse(const FString& Dir)
{
    Course = NewObject<URidePrepCourse>(this);
    FString Err;
    if (!Course->LoadFromDirectory(Dir, Err))
    {
        UE_LOG(LogTemp, Error, TEXT("RidePrep: %s"), *Err);
        Course = nullptr;
        return false;
    }
    UE_LOG(LogTemp, Log, TEXT("RidePrep: loaded %s (%.1f km)"), *Course->Name, Course->DistanceM / 1000.0);
#if WITH_CESIUM
    // Far field: Cesium World Terrain / Photorealistic 3D Tiles around the package origin (ellipsoidal height = H + N)
    if (ACesiumGeoreference* Geo = ACesiumGeoreference::GetDefaultGeoreference(this))
    {
        double N = 0;
        Course->Manifest->GetObjectField(TEXT("origin"))->TryGetNumberField(TEXT("geoidUndulation"), N);
        Geo->SetOriginLongitudeLatitudeHeight(FVector(Course->OriginLon, Course->OriginLat, 0.0 + N));
    }
#endif
    if (RiderClass)
    {
        Rider = GetWorld()->SpawnActor<ARidePrepRider>(RiderClass, Course->PositionAtS(0), FRotator(0, Course->YawAtS(0), 0));
        if (APlayerController* PC = GetWorld()->GetFirstPlayerController()) PC->Possess(Rider);
    }
    BuildRoad();
    // Partition vegetation into cells (added to HISMs as the rider approaches)
    for (int32 k = 0; k < Course->Instances.Num(); ++k)
    {
        const FRidePrepInstance& I = Course->Instances[k];
        InstanceCells.FindOrAdd(FIntPoint(FMath::FloorToInt(I.Enu.X / CellM), FMath::FloorToInt(I.Enu.Y / CellM))).Add(k);
    }
    return true;
}

void ARidePrepWorld::BuildRoad()
{
    const RidePrep::RouteArrays& R = Course->Route;
    const int32 N = (int32)R.Count();
    const double ChunkM = 500;
    UMaterialInterface* RoadMat = Assets ? Assets->RoadMaterial.LoadSynchronous() : nullptr;
    for (double S0 = 0; S0 < Course->DistanceM; S0 += ChunkM)
    {
        const int32 A = FMath::Max(0, FMath::FloorToInt(S0 / R.SpacingM) - 1);
        const int32 B = FMath::Min(N - 1, FMath::CeilToInt((S0 + ChunkM) / R.SpacingM) + 1);
        const RidePrep::Vec3d O = RidePrep::EnuToUe(R.X[A], R.Y[A], R.Z[A]);
        TArray<FVector> V; TArray<int32> T; TArray<FVector> Nrm; TArray<FVector2D> UV; TArray<FLinearColor> Col; TArray<FProcMeshTangent> Tan;
        static const float Lanes[] = { -1.f, -0.5f, 0.f, 0.5f, 1.f };
        for (int32 i = A; i <= B; ++i)
        {
            const double H = R.HeadingRad[i];
            const double Nx = FMath::Cos(H), Ny = -FMath::Sin(H);  // right of travel (ENU)
            const double Hw = R.RoadWidthM[i] / 2.0;
            for (float F : Lanes)
            {
                const double Off = F * Hw;
                const RidePrep::Vec3d P = RidePrep::EnuToUe(R.X[i] + Nx * Off, R.Y[i] + Ny * Off, R.Z[i] + 0.04 - 0.02 * FMath::Abs(Off));
                V.Add(FVector(P.X - O.X, P.Y - O.Y, P.Z - O.Z));
                Nrm.Add(FVector::UpVector);
                UV.Add(FVector2D((F + 1) * 0.5, R.S[i] / 4.0));
                Col.Add(FLinearColor::White);
            }
        }
        const int32 L = UE_ARRAY_COUNT(Lanes);
        for (int32 r = 0; r < B - A; ++r)
            for (int32 q = 0; q < L - 1; ++q)
            {
                const int32 P0 = r * L + q, P1 = P0 + 1, P2 = P0 + L, P3 = P2 + 1;
                // Left-handed UE space: this order faces up (+Z)
                T.Append({ P0, P2, P1, P1, P2, P3 });
            }
        UProceduralMeshComponent* PM = NewObject<UProceduralMeshComponent>(this);
        PM->SetupAttachment(RootComponent);
        PM->RegisterComponent();
        PM->SetWorldLocation(FVector(O.X, O.Y, O.Z));
        PM->CreateMeshSection_LinearColor(0, V, T, Nrm, UV, Col, Tan, false);
        if (RoadMat) PM->SetMaterial(0, RoadMat);
        RoadSections.Add(PM);
    }
}

void ARidePrepWorld::UpdateTerrain(const FVector2D& Enu)
{
    for (const FIntPoint& Tile : Course->TerrainTiles)
    {
        const FVector2D C((Tile.X + 0.5) * Course->TileSizeM, (Tile.Y + 0.5) * Course->TileSizeM);
        const double D = FVector2D::Distance(C, Enu);
        if (D < TerrainRadiusM && !TerrainTiles.Contains(Tile) && !TerrainLoading.Contains(Tile))
        {
            TerrainLoading.Add(Tile);
            TWeakObjectPtr<ARidePrepWorld> Self(this);
            URidePrepCourse* C2 = Course;
            Async(EAsyncExecution::ThreadPool, [Self, C2, Tile]()
            {
                TSharedPtr<FRidePrepTerrainTile> T = MakeShared<FRidePrepTerrainTile>();
                if (!C2->LoadTerrainTile(Tile.X, Tile.Y, *T)) return;
                // Build vertex data off the game thread (stride 2 → 20 m)
                const int32 Stride = 2, M = (T->N - 1) / Stride + 1;
                const double Sp = C2->VertexSpacingM * Stride, Half = C2->TileSizeM / 2;
                TSharedPtr<TArray<FVector>> V = MakeShared<TArray<FVector>>();
                TSharedPtr<TArray<FLinearColor>> Col = MakeShared<TArray<FLinearColor>>();
                TSharedPtr<TArray<int32>> Tri = MakeShared<TArray<int32>>();
                V->Reserve(M * M);
                for (int32 r = 0; r < M; ++r)
                    for (int32 c = 0; c < M; ++c)
                    {
                        const int32 Pr = FMath::Min(r * Stride, T->N - 1), Pc = FMath::Min(c * Stride, T->N - 1);
                        const double Lx = Pc * C2->VertexSpacingM - Half, Ly = Half - Pr * C2->VertexSpacingM;
                        const RidePrep::Vec3d P = RidePrep::EnuToUe(Lx, Ly, T->Heights[Pr * T->N + Pc]);
                        V->Add(FVector(P.X, P.Y, P.Z));
                        Col->Add(LandCoverColor(T->LandCover[Pr * T->N + Pc]));
                    }
                for (int32 r = 0; r < M - 1; ++r)
                    for (int32 c = 0; c < M - 1; ++c)
                    {
                        const int32 A = r * M + c, B = A + 1, D2 = A + M, E = D2 + 1;
                        Tri->Append({ A, B, D2, B, E, D2 });
                    }
                AsyncTask(ENamedThreads::GameThread, [Self, Tile, V, Col, Tri, Sp]()
                {
                    if (!Self.IsValid()) return;
                    ARidePrepWorld* W = Self.Get();
                    W->TerrainLoading.Remove(Tile);
                    TArray<FVector> Nrm; TArray<FVector2D> UV; TArray<FProcMeshTangent> Tan;
                    UProceduralMeshComponent* PM = NewObject<UProceduralMeshComponent>(W);
                    PM->SetupAttachment(W->RootComponent);
                    PM->RegisterComponent();
                    const RidePrep::Vec3d C = RidePrep::EnuToUe((Tile.X + 0.5) * W->Course->TileSizeM, (Tile.Y + 0.5) * W->Course->TileSizeM, 0);
                    PM->SetWorldLocation(FVector(C.X, C.Y, 0));
                    PM->CreateMeshSection_LinearColor(0, *V, *Tri, Nrm, UV, *Col, Tan, true);
                    if (W->Assets) PM->SetMaterial(0, W->Assets->TerrainMaterial.LoadSynchronous());
                    W->TerrainTiles.Add(Tile, PM);
                });
            });
        }
        else if (D > TerrainRadiusM + 2500)
        {
            if (TObjectPtr<UProceduralMeshComponent>* PM = TerrainTiles.Find(Tile))
            {
                (*PM)->DestroyComponent();
                TerrainTiles.Remove(Tile);
            }
        }
    }
}

void ARidePrepWorld::UpdateVegetation(const FVector2D& Enu)
{
    if (!Assets) return;
    for (auto& Cell : InstanceCells)
    {
        if (FoliageCellsLoaded.Contains(Cell.Key)) continue;
        const FVector2D C((Cell.Key.X + 0.5) * CellM, (Cell.Key.Y + 0.5) * CellM);
        if (FVector2D::Distance(C, Enu) > VegetationRadiusM + CellM) continue;
        FoliageCellsLoaded.Add(Cell.Key);
        TMap<FName, TArray<FTransform>> Batches;
        for (int32 k : Cell.Value)
        {
            const FRidePrepInstance& I = Course->Instances[k];
            const FString Cat = Course->InstanceCategories.IsValidIndex(I.Category) ? Course->InstanceCategories[I.Category] : TEXT("prop");
            FName Key(*FString::Printf(TEXT("%s_%d"), *Cat, I.Species));
            if (!Assets->InstanceMeshes.Contains(Key)) Key = FName(*Cat);
            const RidePrep::Vec3d P = RidePrep::EnuToUe(I.Enu.X, I.Enu.Y, I.Enu.Z);
            // Meshes are authored 1 m tall (trees) — scale by the instance height
            const float Sc = Cat.StartsWith(TEXT("tree")) ? I.Height : I.Scale;
            Batches.FindOrAdd(Key).Add(FTransform(FRotator(0, (float)RidePrep::CompassToUeYawDeg(I.Rot), 0), FVector(P.X, P.Y, P.Z), FVector(Sc)));
        }
        for (auto& B : Batches)
        {
            TObjectPtr<UHierarchicalInstancedStaticMeshComponent>& H = Foliage.FindOrAdd(B.Key);
            if (!H)
            {
                const TSoftObjectPtr<UStaticMesh>* M = Assets->InstanceMeshes.Find(B.Key);
                if (!M) continue;
                H = NewObject<UHierarchicalInstancedStaticMeshComponent>(this);
                H->SetStaticMesh(M->LoadSynchronous());
                H->SetupAttachment(RootComponent);
                H->SetCullDistances(0, (int32)(VegetationRadiusM * 100));
                H->RegisterComponent();
            }
            H->AddInstances(B.Value, false, true);
        }
    }
}

void ARidePrepWorld::UpdateChunks(double S)
{
#if WITH_GLTFRUNTIME
    for (const URidePrepCourse::FChunk& C : Course->Chunks)
    {
        const bool Want = C.bBaked && C.SEnd > S - ChunkBehindM && C.SStart < S + ChunkAheadM;
        if (Want && !LoadedChunks.Contains(C.Id) && !ChunksLoading.Contains(C.Id) && C.Lods.Num())
        {
            ChunksLoading.Add(C.Id);
            FglTFRuntimeConfig Cfg;
            Cfg.TransformBaseType = EglTFRuntimeTransformBaseType::YForward;  // package glTF: X east, Y up, Z south
            UglTFRuntimeAsset* Asset = UglTFRuntimeFunctionLibrary::glTFLoadAssetFromFilename(FPaths::Combine(Course->Dir, C.Lods[0]), false, Cfg);
            ChunksLoading.Remove(C.Id);
            if (!Asset) continue;
            const RidePrep::Vec3d O = RidePrep::EnuToUe(C.OriginEnu.X, C.OriginEnu.Y, C.OriginEnu.Z);
            FActorSpawnParameters P;
            P.bDeferConstruction = true;
            AglTFRuntimeAssetActor* A = GetWorld()->SpawnActor<AglTFRuntimeAssetActor>(AglTFRuntimeAssetActor::StaticClass(), FTransform(FVector(O.X, O.Y, O.Z)), P);
            A->Asset = Asset;
            A->FinishSpawning(FTransform(FVector(O.X, O.Y, O.Z)));
            LoadedChunks.Add(C.Id, A);
            // Hide the runtime road section this chunk replaces
            if (RoadSections.IsValidIndex(C.Id)) RoadSections[C.Id]->SetVisibility(false);
        }
        else if (!Want && LoadedChunks.Contains(C.Id))
        {
            LoadedChunks[C.Id]->Destroy();
            LoadedChunks.Remove(C.Id);
            if (RoadSections.IsValidIndex(C.Id)) RoadSections[C.Id]->SetVisibility(true);
        }
    }
#endif
}

void ARidePrepWorld::UpdateEnvironment(const FRidePrepStreamState& S)
{
    if (Sun)
    {
        // Light travels from the sun to the ground: yaw = azimuth + 90° in UE (X east, Y south), pitch = −elevation
        Sun->SetActorRotation(FRotator(-S.SunElevationDeg, S.SunAzimuthDeg + 90.f, 0));
        Sun->GetLightComponent()->SetIntensity(FMath::Lerp(10.f, 2.5f, S.Weather.CloudCover) * FMath::Clamp((S.SunElevationDeg + 4.f) / 14.f, 0.f, 1.f));
    }
    if (Fog) Fog->GetComponent()->SetFogDensity(FMath::Clamp(0.02f * 20000.f / FMath::Max(S.Weather.VisibilityM, 200.f), 0.005f, 0.5f));
    if (Assets && !Assets->EnvironmentParameters.IsNull())
    {
        UMaterialParameterCollection* MPC = Assets->EnvironmentParameters.LoadSynchronous();
        const float To = FMath::DegreesToRadians(S.Wind.DirRider + 180.f);
        // Direction the wind blows toward, in UE XY (X east, Y south)
        UKismetMaterialLibrary::SetScalarParameterValue(this, MPC, TEXT("WindDirX"), FMath::Sin(To));
        UKismetMaterialLibrary::SetScalarParameterValue(this, MPC, TEXT("WindDirY"), -FMath::Cos(To));
        UKismetMaterialLibrary::SetScalarParameterValue(this, MPC, TEXT("WindStrength"), S.Wind.URider);
        UKismetMaterialLibrary::SetScalarParameterValue(this, MPC, TEXT("Gust"), S.Wind.Gust);
        UKismetMaterialLibrary::SetScalarParameterValue(this, MPC, TEXT("Wetness"), FMath::Clamp(S.Weather.PrecipMmH / 2.f, 0.f, 1.f));
        UKismetMaterialLibrary::SetScalarParameterValue(this, MPC, TEXT("CloudCover"), S.Weather.CloudCover);
    }
}

void ARidePrepWorld::Tick(float Dt)
{
    Super::Tick(Dt);
    if (!Course) return;
    const FRidePrepStreamState& St = Stream->Latest;
    const double S = Stream->IsConnected() ? Stream->InterpolatedS(FPlatformTime::Seconds()) : 0.0;
    if (Rider) Rider->ApplyState(St, Course->PositionAtS(S), Course->YawAtS(S), Dt);
    if (FMath::Abs(S - LastStreamS) > 50.0)
    {
        LastStreamS = S;
        const RidePrep::RoutePose P = RidePrep::PoseAt(Course->Route, S);
        UpdateTerrain(FVector2D(P.X, P.Y));
        UpdateVegetation(FVector2D(P.X, P.Y));
        UpdateChunks(S);
    }
    UpdateEnvironment(St);
}

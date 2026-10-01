#include "RidePrepCourse.h"

#include "Dom/JsonObject.h"
#include "IImageWrapper.h"
#include "IImageWrapperModule.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Modules/ModuleManager.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

static bool LoadJson(const FString& Path, TSharedPtr<FJsonObject>& Out)
{
    FString Text;
    if (!FFileHelper::LoadFileToString(Text, *Path)) return false;
    return FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Out) && Out.IsValid();
}

bool URidePrepCourse::LoadFromDirectory(const FString& InDir, FString& OutError)
{
    Dir = InDir;
    if (!LoadJson(FPaths::Combine(Dir, TEXT("manifest.json")), Manifest) && !LoadJson(FPaths::Combine(Dir, TEXT("manifest.partial.json")), Manifest))
    {
        OutError = TEXT("manifest.json not found or invalid");
        return false;
    }
    if (Manifest->GetStringField(TEXT("schemaVersion")) != TEXT("1.0.0"))
    {
        OutError = TEXT("unsupported schemaVersion");
        return false;
    }
    Name = Manifest->GetStringField(TEXT("name"));
    CourseId = Manifest->GetStringField(TEXT("courseId"));
    const TSharedPtr<FJsonObject> Origin = Manifest->GetObjectField(TEXT("origin"));
    OriginLat = Origin->GetNumberField(TEXT("lat"));
    OriginLon = Origin->GetNumberField(TEXT("lon"));
    OriginH = Origin->GetNumberField(TEXT("hOrthometric"));
    DistanceM = Manifest->GetObjectField(TEXT("stats"))->GetNumberField(TEXT("distanceM"));

    // route.bin
    const TSharedPtr<FJsonObject> RouteJ = Manifest->GetObjectField(TEXT("route"));
    TArray<uint8> Bytes;
    if (!FFileHelper::LoadFileToArray(Bytes, *FPaths::Combine(Dir, RouteJ->GetStringField(TEXT("file")))))
    {
        OutError = TEXT("route.bin missing");
        return false;
    }
    std::vector<RidePrep::ArrayLayout> Layout;
    for (const TSharedPtr<FJsonValue>& V : RouteJ->GetArrayField(TEXT("arrays")))
    {
        const TSharedPtr<FJsonObject> A = V->AsObject();
        Layout.push_back({ TCHAR_TO_UTF8(*A->GetStringField(TEXT("name"))), A->GetStringField(TEXT("type")) == TEXT("float32"), (size_t)A->GetNumberField(TEXT("offset")) });
    }
    try
    {
        Route = RidePrep::DecodeRoute(Bytes.GetData(), Bytes.Num(), (size_t)RouteJ->GetNumberField(TEXT("count")), RouteJ->GetNumberField(TEXT("sampleSpacingM")), Layout);
    }
    catch (const std::exception& E)
    {
        OutError = UTF8_TO_TCHAR(E.what());
        return false;
    }

    // instances.bin (28-byte records)
    const TSharedPtr<FJsonObject> InstJ = Manifest->GetObjectField(TEXT("instances"));
    for (const TSharedPtr<FJsonValue>& V : InstJ->GetArrayField(TEXT("categories"))) InstanceCategories.Add(V->AsString());
    TArray<uint8> IB;
    if (FFileHelper::LoadFileToArray(IB, *FPaths::Combine(Dir, InstJ->GetStringField(TEXT("file")))))
    {
        const int32 RB = (int32)InstJ->GetNumberField(TEXT("recordBytes"));
        const int32 N = IB.Num() / RB;
        Instances.SetNumUninitialized(N);
        for (int32 k = 0; k < N; ++k)
        {
            const uint8* R = IB.GetData() + k * RB;
            FRidePrepInstance& I = Instances[k];
            float F[6];
            FMemory::Memcpy(F, R, 24);
            I.Enu = FVector3f(F[0], F[1], F[2]);
            I.Rot = F[3]; I.Scale = F[4]; I.Height = F[5];
            I.Category = R[24]; I.Species = R[25];
        }
    }

    // Terrain tiles and chunks
    const TSharedPtr<FJsonObject> Quick = Manifest->GetObjectField(TEXT("terrain"))->GetObjectField(TEXT("quickTier"));
    TileSizeM = Quick->GetNumberField(TEXT("tileSizeM"));
    VertexSpacingM = Quick->GetNumberField(TEXT("vertexSpacingM"));
    for (const TSharedPtr<FJsonValue>& V : Quick->GetArrayField(TEXT("tiles")))
        TerrainTiles.Add(FIntPoint((int32)V->AsObject()->GetNumberField(TEXT("i")), (int32)V->AsObject()->GetNumberField(TEXT("j"))));
    for (const TSharedPtr<FJsonValue>& V : Manifest->GetArrayField(TEXT("chunks")))
    {
        const TSharedPtr<FJsonObject> C = V->AsObject();
        FChunk Ch;
        Ch.Id = (int32)C->GetNumberField(TEXT("id"));
        Ch.SStart = C->GetNumberField(TEXT("sStart"));
        Ch.SEnd = C->GetNumberField(TEXT("sEnd"));
        Ch.bBaked = C->GetStringField(TEXT("status")) == TEXT("baked");
        const TArray<TSharedPtr<FJsonValue>>* O;
        if (C->TryGetArrayField(TEXT("origin"), O) && O->Num() == 3) Ch.OriginEnu = FVector((*O)[0]->AsNumber(), (*O)[1]->AsNumber(), (*O)[2]->AsNumber());
        for (const TSharedPtr<FJsonValue>& L : C->GetArrayField(TEXT("lod"))) Ch.Lods.Add(L->AsString());
        Chunks.Add(Ch);
    }
    return true;
}

bool URidePrepCourse::LoadTerrainTile(int32 I, int32 J, FRidePrepTerrainTile& Out) const
{
    IImageWrapperModule& IW = FModuleManager::LoadModuleChecked<IImageWrapperModule>(TEXT("ImageWrapper"));
    auto Decode = [&](const FString& Rel, TArray64<uint8>& Raw, int32& W) -> bool
    {
        TArray<uint8> Png;
        if (!FFileHelper::LoadFileToArray(Png, *FPaths::Combine(Dir, Rel))) return false;
        TSharedPtr<IImageWrapper> Img = IW.CreateImageWrapper(EImageFormat::PNG);
        if (!Img->SetCompressed(Png.GetData(), Png.Num())) return false;
        W = Img->GetWidth();
        return Img->GetRaw(ERGBFormat::RGBA, 8, Raw);
    };
    TArray64<uint8> Dem, Lc;
    int32 W = 0, W2 = 0;
    const FString Name = FString::Printf(TEXT("%d_%d"), I, J);
    if (!Decode(FString::Printf(TEXT("dem/%s.png"), *Name), Dem, W) || !Decode(FString::Printf(TEXT("lc/%s.png"), *Name), Lc, W2)) return false;
    Out.I = I; Out.J = J; Out.N = W;
    Out.Heights.SetNumUninitialized(W * W);
    Out.LandCover.SetNumUninitialized(W * W);
    for (int32 k = 0; k < W * W; ++k)
    {
        // Terrarium: (R·256 + G + B/256) − 32768
        Out.Heights[k] = Dem[k * 4] * 256.f + Dem[k * 4 + 1] + Dem[k * 4 + 2] / 256.f - 32768.f;
        Out.LandCover[k] = Lc[k * 4];
    }
    return true;
}

FVector URidePrepCourse::PositionAtS(double S) const
{
    const RidePrep::RoutePose P = RidePrep::PoseAt(Route, S);
    const RidePrep::Vec3d U = RidePrep::EnuToUe(P.X, P.Y, P.Z);
    return FVector(U.X, U.Y, U.Z);
}

float URidePrepCourse::YawAtS(double S) const
{
    return (float)RidePrep::CompassToUeYawDeg(RidePrep::PoseAt(Route, S).HeadingRad);
}

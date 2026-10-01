using System.IO;
using UnrealBuildTool;

public class RidePrepRuntime : ModuleRules
{
    public RidePrepRuntime(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        CppStandard = CppStandardVersion.Cpp20;
        PublicDependencyModuleNames.AddRange(new[] { "Core", "CoreUObject", "Engine", "UMG", "ProceduralMeshComponent", "Slate", "SlateCore" });
        PrivateDependencyModuleNames.AddRange(new[] { "WebSockets", "Json", "JsonUtilities", "ImageWrapper", "RenderCore" });

        // Optional integrations: compiled in when the plugins are present in the project.
        string ProjectPlugins = Path.Combine(Target.ProjectFile?.Directory.FullName ?? "", "Plugins");
        bool HasGltf = Directory.Exists(Path.Combine(ProjectPlugins, "glTFRuntime"));
        bool HasCesium = Directory.Exists(Path.Combine(ProjectPlugins, "CesiumForUnreal"));
        if (HasGltf) PrivateDependencyModuleNames.Add("glTFRuntime");
        if (HasCesium) PrivateDependencyModuleNames.Add("CesiumRuntime");
        PublicDefinitions.Add("WITH_GLTFRUNTIME=" + (HasGltf ? "1" : "0"));
        PublicDefinitions.Add("WITH_CESIUM=" + (HasCesium ? "1" : "0"));
    }
}

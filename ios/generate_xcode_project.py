#!/usr/bin/env python3
"""Generate MagicFormsMobile.xcodeproj from sources under MagicFormsMobile/."""

from __future__ import annotations

import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "MagicFormsMobile.xcodeproj" / "project.pbxproj"

SWIFT_FILES = [
    "MagicFormsMobileApp.swift",
    "Config/APIConfig.swift",
    "Models/AuthModels.swift",
    "Models/HomeModels.swift",
    "Models/SignatureModels.swift",
    "Services/AuthAPI.swift",
    "Services/LanguageManager.swift",
    "Services/HomeAPI.swift",
    "Services/FormSubmitAPI.swift",
    "Services/SignatureAPI.swift",
    "Services/SearchAPI.swift",
    "Services/KeychainTokenStore.swift",
    "Services/BiometricPreferences.swift",
    "Services/BiometricLockManager.swift",
    "Services/FormDraftStore.swift",
    "Services/NetworkMonitor.swift",
    "Services/OfflineSubmitQueue.swift",
    "Services/DeviceAPI.swift",
    "Services/PushRegistration.swift",
    "Services/LoginIdentityParser.swift",
    "ViewModels/AuthViewModel.swift",
    "Views/LoginView.swift",
    "Views/MainShellView.swift",
    "Views/AppBannerTitle.swift",
    "Views/BannerLogoImage.swift",
    "Views/ListFilterBar.swift",
    "Views/FormsHomeView.swift",
    "Views/FormIntroView.swift",
    "Views/FormSubmitView.swift",
    "Views/PendingRelatedView.swift",
    "Views/InboxView.swift",
    "Views/InboxDetailView.swift",
    "Views/DrawerMenuView.swift",
    "Views/MySignaturesView.swift",
    "Views/SignaturePadView.swift",
    "Views/SubmissionSearchView.swift",
    "Views/OrganizationLoginField.swift",
    "Views/HomeView.swift",
    "Views/RootView.swift",
    "Views/AppLockView.swift",
    "Views/AppLogoView.swift",
    "Views/DocumentPreviewView.swift",
    "Views/LanguagePickerView.swift",
]

# Info.plist is referenced via INFOPLIST_FILE — do not copy in Resources phase.
RESOURCE_FILES = [
    "Resources/Assets.xcassets",
]


def uid() -> str:
    return uuid.uuid4().hex[:24].upper()


def main() -> None:
    ids: dict[str, str] = {}

    def i(key: str) -> str:
        if key not in ids:
            ids[key] = uid()
        return ids[key]

    project = i("project")
    target = i("target")
    product = i("product")
    sources_phase = i("sources_phase")
    resources_phase = i("resources_phase")
    frameworks_phase = i("frameworks_phase")
    proj_config_list = i("proj_config_list")
    target_config_list = i("target_config_list")
    debug_proj = i("debug_proj")
    release_proj = i("release_proj")
    debug_tgt = i("debug_tgt")
    release_tgt = i("release_tgt")
    main_group = i("main_group")
    products_group = i("products_group")
    app_group = i("app_group")

    entries: list[dict] = []
    for rel in SWIFT_FILES:
        entries.append(
            {
                "rel": rel,
                "ref": i(f"ref:{rel}"),
                "bf": i(f"bf:{rel}"),
                "typ": "sourcecode.swift",
                "phase": "sources",
            }
        )
    for rel in RESOURCE_FILES:
        typ = "folder.assetcatalog" if rel.endswith(".xcassets") else "text.plist.xml"
        entries.append(
            {
                "rel": rel,
                "ref": i(f"ref:{rel}"),
                "bf": i(f"bf:{rel}"),
                "typ": typ,
                "phase": "resources",
            }
        )

    build_file_section = "\n".join(
        f"\t\t{e['bf']} /* {Path(e['rel']).name} in {e['phase'].title()} */ = {{isa = PBXBuildFile; fileRef = {e['ref']} /* {Path(e['rel']).name} */; }};"
        for e in entries
    )
    file_ref_lines = "\n".join(
        f"\t\t{e['ref']} /* {Path(e['rel']).name} */ = {{isa = PBXFileReference; lastKnownFileType = {e['typ']}; path = {e['rel']}; sourceTree = \"<group>\"; }};"
        for e in entries
    )
    children_app = "\n".join(
        f"\t\t\t\t{e['ref']} /* {Path(e['rel']).name} */," for e in entries
    )
    swift_build_lines = "\n".join(
        f"\t\t\t\t{e['bf']} /* {Path(e['rel']).name} in Sources */,"
        for e in entries
        if e["phase"] == "sources"
    )
    res_build_lines = "\n".join(
        f"\t\t\t\t{e['bf']} /* {Path(e['rel']).name} in Resources */,"
        for e in entries
        if e["phase"] == "resources"
    )

    pbx = f"""// !$*UTF8*$!
{{
\tarchiveVersion = 1;
\tclasses = {{
\t}};
\tobjectVersion = 56;
\tobjects = {{

/* Begin PBXBuildFile section */
{build_file_section}
/* End PBXBuildFile section */

/* Begin PBXFileReference section */
\t\t{product} /* MagicFormsMobile.app */ = {{isa = PBXFileReference; explicitFileType = wrapper.application; includeInIndex = 0; path = MagicFormsMobile.app; sourceTree = BUILT_PRODUCTS_DIR; }};
{file_ref_lines}
/* End PBXFileReference section */

/* Begin PBXFrameworksBuildPhase section */
\t\t{frameworks_phase} /* Frameworks */ = {{
\t\t\tisa = PBXFrameworksBuildPhase;
\t\t\tbuildActionMask = 2147483647;
\t\t\tfiles = (
\t\t\t);
\t\t\trunOnlyForDeploymentPostprocessing = 0;
\t\t}};
/* End PBXFrameworksBuildPhase section */

/* Begin PBXGroup section */
\t\t{main_group} = {{
\t\t\tisa = PBXGroup;
\t\t\tchildren = (
\t\t\t\t{app_group} /* MagicFormsMobile */,
\t\t\t\t{products_group} /* Products */,
\t\t\t);
\t\t\tsourceTree = \"<group>\";
\t\t}};
\t\t{products_group} /* Products */ = {{
\t\t\tisa = PBXGroup;
\t\t\tchildren = (
\t\t\t\t{product} /* MagicFormsMobile.app */,
\t\t\t);
\t\t\tname = Products;
\t\t\tsourceTree = \"<group>\";
\t\t}};
\t\t{app_group} /* MagicFormsMobile */ = {{
\t\t\tisa = PBXGroup;
\t\t\tchildren = (
{children_app}
\t\t\t);
\t\t\tpath = MagicFormsMobile;
\t\t\tsourceTree = \"<group>\";
\t\t}};
/* End PBXGroup section */

/* Begin PBXNativeTarget section */
\t\t{target} /* MagicFormsMobile */ = {{
\t\t\tisa = PBXNativeTarget;
\t\t\tbuildConfigurationList = {target_config_list} /* Build configuration list for PBXNativeTarget "MagicFormsMobile" */;
\t\t\tbuildPhases = (
\t\t\t\t{sources_phase} /* Sources */,
\t\t\t\t{frameworks_phase} /* Frameworks */,
\t\t\t\t{resources_phase} /* Resources */,
\t\t\t);
\t\t\tbuildRules = (
\t\t\t);
\t\t\tdependencies = (
\t\t\t);
\t\t\tname = MagicFormsMobile;
\t\t\tproductName = MagicFormsMobile;
\t\t\tproductReference = {product} /* MagicFormsMobile.app */;
\t\t\tproductType = \"com.apple.product-type.application\";
\t\t}};
/* End PBXNativeTarget section */

/* Begin PBXProject section */
\t\t{project} /* Project object */ = {{
\t\t\tisa = PBXProject;
\t\t\tattributes = {{
\t\t\t\tBuildIndependentTargetsInParallel = 1;
\t\t\t\tLastSwiftUpdateCheck = 1500;
\t\t\t\tLastUpgradeCheck = 1500;
\t\t\t\tTargetAttributes = {{
\t\t\t\t\t{target} = {{
\t\t\t\t\t\tCreatedOnToolsVersion = 15.0;
\t\t\t\t\t}};
\t\t\t\t}};
\t\t\t}};
\t\t\tbuildConfigurationList = {proj_config_list} /* Build configuration list for PBXProject "MagicFormsMobile" */;
\t\t\tcompatibilityVersion = \"Xcode 14.0\";
\t\t\tdevelopmentRegion = en;
\t\t\thasScannedForEncodings = 0;
\t\t\tknownRegions = (
\t\t\t\ten,
\t\t\t\tBase,
\t\t\t);
\t\t\tmainGroup = {main_group};
\t\t\tproductRefGroup = {products_group} /* Products */;
\t\t\tprojectDirPath = \"\";
\t\t\tprojectRoot = \"\";
\t\t\ttargets = (
\t\t\t\t{target} /* MagicFormsMobile */,
\t\t\t);
\t\t}};
/* End PBXProject section */

/* Begin PBXResourcesBuildPhase section */
\t\t{resources_phase} /* Resources */ = {{
\t\t\tisa = PBXResourcesBuildPhase;
\t\t\tbuildActionMask = 2147483647;
\t\t\tfiles = (
{res_build_lines}
\t\t\t);
\t\t\trunOnlyForDeploymentPostprocessing = 0;
\t\t}};
/* End PBXResourcesBuildPhase section */

/* Begin PBXSourcesBuildPhase section */
\t\t{sources_phase} /* Sources */ = {{
\t\t\tisa = PBXSourcesBuildPhase;
\t\t\tbuildActionMask = 2147483647;
\t\t\tfiles = (
{swift_build_lines}
\t\t\t);
\t\t\trunOnlyForDeploymentPostprocessing = 0;
\t\t}};
/* End PBXSourcesBuildPhase section */

/* Begin XCBuildConfiguration section */
\t\t{debug_proj} /* Debug */ = {{
\t\t\tisa = XCBuildConfiguration;
\t\t\tbuildSettings = {{
\t\t\t\tALWAYS_SEARCH_USER_PATHS = NO;
\t\t\t\tCLANG_ENABLE_MODULES = YES;
\t\t\t\tCLANG_ENABLE_OBJC_ARC = YES;
\t\t\t\tCOPY_PHASE_STRIP = NO;
\t\t\t\tDEBUG_INFORMATION_FORMAT = dwarf;
\t\t\t\tENABLE_TESTABILITY = YES;
\t\t\t\tGCC_DYNAMIC_NO_PIC = NO;
\t\t\t\tGCC_OPTIMIZATION_LEVEL = 0;
\t\t\t\tGCC_PREPROCESSOR_DEFINITIONS = (
\t\t\t\t\t\"DEBUG=1\",
\t\t\t\t\t\"$(inherited)\",
\t\t\t\t);
\t\t\t\tIPHONEOS_DEPLOYMENT_TARGET = 17.0;
\t\t\t\tMTL_ENABLE_DEBUG_INFO = INCLUDE_SOURCE;
\t\t\t\tONLY_ACTIVE_ARCH = YES;
\t\t\t\tSDKROOT = iphoneos;
\t\t\t\tSWIFT_ACTIVE_COMPILATION_CONDITIONS = DEBUG;
\t\t\t\tSWIFT_OPTIMIZATION_LEVEL = \"-Onone\";
\t\t\t}};
\t\t\tname = Debug;
\t\t}};
\t\t{release_proj} /* Release */ = {{
\t\t\tisa = XCBuildConfiguration;
\t\t\tbuildSettings = {{
\t\t\t\tALWAYS_SEARCH_USER_PATHS = NO;
\t\t\t\tCLANG_ENABLE_MODULES = YES;
\t\t\t\tCLANG_ENABLE_OBJC_ARC = YES;
\t\t\t\tCOPY_PHASE_STRIP = NO;
\t\t\t\tDEBUG_INFORMATION_FORMAT = \"dwarf-with-dsym\";
\t\t\t\tENABLE_NS_ASSERTIONS = NO;
\t\t\t\tIPHONEOS_DEPLOYMENT_TARGET = 17.0;
\t\t\t\tMTL_ENABLE_DEBUG_INFO = NO;
\t\t\t\tSDKROOT = iphoneos;
\t\t\t\tSWIFT_COMPILATION_MODE = wholemodule;
\t\t\t\tVALIDATE_PRODUCT = YES;
\t\t\t}};
\t\t\tname = Release;
\t\t}};
\t\t{debug_tgt} /* Debug */ = {{
\t\t\tisa = XCBuildConfiguration;
\t\t\tbuildSettings = {{
\t\t\t\tASSETCATALOG_COMPILER_APPICON_NAME = AppIcon;
\t\t\t\tCODE_SIGN_STYLE = Automatic;
\t\t\t\tCURRENT_PROJECT_VERSION = 1;
\t\t\t\tGENERATE_INFOPLIST_FILE = NO;
\t\t\t\tINFOPLIST_FILE = MagicFormsMobile/Resources/Info.plist;
\t\t\t\tIPHONEOS_DEPLOYMENT_TARGET = 17.0;
\t\t\t\tLD_RUNPATH_SEARCH_PATHS = (
\t\t\t\t\t\"$(inherited)\",
\t\t\t\t\t\"@executable_path/Frameworks\",
\t\t\t\t);
\t\t\t\tAPI_BASE_URL = \"http://127.0.0.1:8000\";
\t\t\t\tMARKETING_VERSION = 1.0;
\t\t\t\tPRODUCT_BUNDLE_IDENTIFIER = com.magicforms.mobile;
\t\t\t\tPRODUCT_NAME = \"$(TARGET_NAME)\";
\t\t\t\tSWIFT_EMIT_LOC_STRINGS = YES;
\t\t\t\tSWIFT_VERSION = 5.0;
\t\t\t\tTARGETED_DEVICE_FAMILY = \"1,2\";
\t\t\t}};
\t\t\tname = Debug;
\t\t}};
\t\t{release_tgt} /* Release */ = {{
\t\t\tisa = XCBuildConfiguration;
\t\t\tbuildSettings = {{
\t\t\t\tASSETCATALOG_COMPILER_APPICON_NAME = AppIcon;
\t\t\t\tCODE_SIGN_STYLE = Automatic;
\t\t\t\tCURRENT_PROJECT_VERSION = 1;
\t\t\t\tGENERATE_INFOPLIST_FILE = NO;
\t\t\t\tINFOPLIST_FILE = MagicFormsMobile/Resources/Info.plist;
\t\t\t\tIPHONEOS_DEPLOYMENT_TARGET = 17.0;
\t\t\t\tLD_RUNPATH_SEARCH_PATHS = (
\t\t\t\t\t\"$(inherited)\",
\t\t\t\t\t\"@executable_path/Frameworks\",
\t\t\t\t);
\t\t\t\tAPI_BASE_URL = \"https://YOUR_DOMAIN.example\";
\t\t\t\tMARKETING_VERSION = 1.0;
\t\t\t\tPRODUCT_BUNDLE_IDENTIFIER = com.magicforms.mobile;
\t\t\t\tPRODUCT_NAME = \"$(TARGET_NAME)\";
\t\t\t\tSWIFT_EMIT_LOC_STRINGS = YES;
\t\t\t\tSWIFT_VERSION = 5.0;
\t\t\t\tTARGETED_DEVICE_FAMILY = \"1,2\";
\t\t\t}};
\t\t\tname = Release;
\t\t}};
/* End XCBuildConfiguration section */

/* Begin XCConfigurationList section */
\t\t{proj_config_list} /* Build configuration list for PBXProject "MagicFormsMobile" */ = {{
\t\t\tisa = XCConfigurationList;
\t\t\tbuildConfigurations = (
\t\t\t\t{debug_proj} /* Debug */,
\t\t\t\t{release_proj} /* Release */,
\t\t\t);
\t\t\tdefaultConfigurationIsVisible = 0;
\t\t\tdefaultConfigurationName = Release;
\t\t}};
\t\t{target_config_list} /* Build configuration list for PBXNativeTarget "MagicFormsMobile" */ = {{
\t\t\tisa = XCConfigurationList;
\t\t\tbuildConfigurations = (
\t\t\t\t{debug_tgt} /* Debug */,
\t\t\t\t{release_tgt} /* Release */,
\t\t\t);
\t\t\tdefaultConfigurationIsVisible = 0;
\t\t\tdefaultConfigurationName = Release;
\t\t}};
/* End XCConfigurationList section */
\t}};
\trootObject = {project} /* Project object */;
}}
"""

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(pbx, encoding="utf-8")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()

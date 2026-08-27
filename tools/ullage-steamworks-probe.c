/*
 * Small Steamworks acceptance probe.
 *
 * This deliberately uses the flat C exports from a game's steam_api DLL
 * instead of shipping Valve's SDK headers or linking against a replacement
 * Steam client.  The DLL remains the game's own copy; Ullage only supplies
 * the Wine/lsteamclient boundary around this process.
 */

#include <windows.h>

#include <stdint.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* SteamAPI_Init and SteamAPI_RestartAppIfNecessary return C++ bool.  Reading
 * them as int can expose undefined upper bits on Windows x64. */
typedef unsigned char (__cdecl *BoolFn)(void);
typedef unsigned char (__cdecl *RestartFn)(uint32_t);
typedef void (__cdecl *VoidFn)(void);
typedef int (__cdecl *GetIntFn)(void);
typedef uint32_t (__cdecl *GetAppIdFn)(void *);
typedef void *(__cdecl *CreateInterfaceFn)(const char *);
typedef void *(__cdecl *SteamClientFn)(void);
typedef void *(__cdecl *GetUserInterfaceFn)(void *, int, int, const char *);
typedef void *(__cdecl *GetUtilsInterfaceFn)(void *, int, const char *);
typedef int (__cdecl *UserBoolFn)(void *);
typedef uint64_t (__cdecl *UserSteamIdFn)(void *);
typedef int (__cdecl *AppsBoolFn)(void *);
typedef int (__cdecl *AppsBoolAppFn)(void *, uint32_t);
typedef int (__cdecl *AppsCountFn)(void *, uint32_t);
typedef int (__cdecl *AppsDlcFn)(void *, uint32_t, int, uint32_t *, int *,
                                 char *, int);
typedef int (__cdecl *StatsRequestFn)(void *);
typedef int (__cdecl *StatsCountFn)(void *);
typedef const char *(__cdecl *StatsNameFn)(void *, int);
typedef int (__cdecl *StatsAchievementFn)(void *, const char *, int *);
typedef int (__cdecl *UtilsOverlayFn)(void *);

#define INIT_TIMEOUT_MS 10000

#ifdef _WIN64
#define API_DLL "steam_api64.dll"
#define PROBE_ARCH "win64"
#else
#define API_DLL "steam_api.dll"
#define PROBE_ARCH "win32"
#endif

static void probe_log(const char *format, ...) {
    va_list args;
    va_start(args, format);
    vfprintf(stdout, format, args);
    va_end(args);

    FILE *file = fopen("ullage-steamworks-probe.log", "a");
    if (!file) return;
    va_start(args, format);
    vfprintf(file, format, args);
    va_end(args);
    fclose(file);
}

#define printf probe_log

static DWORD WINAPI init_timeout_thread(void *argument) {
    HANDLE done = (HANDLE)argument;
    if (WaitForSingleObject(done, INIT_TIMEOUT_MS) == WAIT_TIMEOUT) {
        printf("steam_api_init_timeout=1\n");
        ExitProcess(124);
    }
    return 0;
}

static unsigned char init_with_timeout(BoolFn init) {
    HANDLE done = CreateEventA(NULL, TRUE, FALSE, NULL);
    HANDLE watchdog = done ? CreateThread(NULL, 0, init_timeout_thread, done, 0, NULL) : NULL;
    if (!done || !watchdog) {
        printf("steam_api_init_watchdog=0\n");
        if (watchdog) CloseHandle(watchdog);
        if (done) CloseHandle(done);
        ExitProcess(125);
    }

    unsigned char result = init();
    SetEvent(done);
    WaitForSingleObject(watchdog, INFINITE);
    CloseHandle(watchdog);
    CloseHandle(done);
    return result;
}

static FARPROC symbol(HMODULE module, const char *name) {
    FARPROC result = GetProcAddress(module, name);
    if (!result) fprintf(stderr, "missing_symbol=%s\n", name);
    return result;
}

/* GetProcAddress returns FARPROC, while each export has its own C signature.
 * A union keeps the unavoidable Windows loader conversion in one place and
 * lets the probe compile cleanly with -Wcast-function-type. */
#define LOAD_FN(module, name, type) \
    ({ union { FARPROC raw; type typed; } loaded; \
       loaded.raw = symbol((module), (name)); loaded.typed; })

static void *interface_with_versions(CreateInterfaceFn create,
                                     const char *const *versions,
                                     size_t count) {
    for (size_t i = 0; i < count; ++i) {
        void *value = create(versions[i]);
        if (value) {
            printf("interface=%s\n", versions[i]);
            return value;
        }
    }
    return NULL;
}

static void *user_interface(GetUserInterfaceFn get, void *client, int user,
                            int pipe, const char *const *versions,
                            size_t count) {
    for (size_t i = 0; i < count; ++i) {
        void *value = get(client, user, pipe, versions[i]);
        if (value) {
            printf("user_interface=%s\n", versions[i]);
            return value;
        }
    }
    return NULL;
}

static void *utils_interface(GetUtilsInterfaceFn get, void *client, int pipe,
                             const char *const *versions, size_t count) {
    for (size_t i = 0; i < count; ++i) {
        void *value = get(client, pipe, versions[i]);
        if (value) {
            printf("utils_interface=%s\n", versions[i]);
            return value;
        }
    }
    return NULL;
}

static int expected_app_id(int argc, char **argv) {
    for (int i = 1; i + 1 < argc; ++i) {
        if (strcmp(argv[i], "--appid") == 0) return (int)strtol(argv[i + 1], NULL, 10);
    }
    return 0;
}

static int has_flag(int argc, char **argv, const char *flag) {
    for (int i = 1; i < argc; ++i) {
        if (strcmp(argv[i], flag) == 0) return 1;
    }
    return 0;
}

static void log_environment(void) {
    static const char *const names[] = {
        "SteamAppId", "SteamGameId", "SteamClientLaunch", "SteamOverlayGameId",
        "SteamEnv", "SteamAppUser", "SteamUser", "Steam3Master",
        "SteamVirtualGamepadInfo", "SteamVirtualGamepadInfo_Proton",
        "STEAM_COMPAT_CLIENT_INSTALL_PATH", "STEAM_COMPAT_DATA_PATH",
        "STEAM_DYLD_INSERT_LIBRARIES", "DYLD_INSERT_LIBRARIES",
        "STEAM_CLIENT_CONFIG_FILE", "STEAM_APP_BUNDLE_PATH", "SteamPath"
    };

    for (size_t i = 0; i < sizeof(names) / sizeof(names[0]); ++i) {
        const char *value = getenv(names[i]);
        if (value) printf("env_%s=%s\n", names[i], value);
    }
}

int main(int argc, char **argv) {
    setvbuf(stdout, NULL, _IONBF, 0);
    const int expected = expected_app_id(argc, argv);
    const int check_running = has_flag(argc, argv, "--running-check");
    const int check_restart = has_flag(argc, argv, "--restart");
    const char *const client_versions[] = {
        "SteamClient020", "SteamClient019", "SteamClient017"
    };
    const char *const user_versions[] = {
        "SteamUser023", "SteamUser022", "SteamUser021", "SteamUser020",
        "SteamUser019"
    };
    const char *const apps_versions[] = {
        "STEAMAPPS_INTERFACE_VERSION008", "STEAMAPPS_INTERFACE_VERSION007",
        "STEAMAPPS_INTERFACE_VERSION006"
    };
    const char *const stats_versions[] = {
        "STEAMUSERSTATS_INTERFACE_VERSION012",
        "STEAMUSERSTATS_INTERFACE_VERSION011",
        "STEAMUSERSTATS_INTERFACE_VERSION010"
    };
    const char *const utils_versions[] = {
        "SteamUtils010", "SteamUtils009", "SteamUtils008"
    };

    printf("probe_arch=%s\napi_dll=%s\n", PROBE_ARCH, API_DLL);
    if (has_flag(argc, argv, "--env-only")) {
        log_environment();
        return 0;
    }
    HMODULE api = LoadLibraryA(API_DLL);
    if (!api) {
        printf("steam_api_load=0\n");
        return 1;
    }
    printf("steam_api_load=1\n");

    BoolFn init = LOAD_FN(api, "SteamAPI_Init", BoolFn);
    RestartFn restart = LOAD_FN(
        api, "SteamAPI_RestartAppIfNecessary", RestartFn);
    BoolFn is_running = LOAD_FN(api, "SteamAPI_IsSteamRunning", BoolFn);
    VoidFn run_callbacks = LOAD_FN(api, "SteamAPI_RunCallbacks", VoidFn);
    VoidFn shutdown = LOAD_FN(api, "SteamAPI_Shutdown", VoidFn);
    GetIntFn get_pipe = LOAD_FN(api, "SteamAPI_GetHSteamPipe", GetIntFn);
    GetIntFn get_user = LOAD_FN(api, "SteamAPI_GetHSteamUser", GetIntFn);
    CreateInterfaceFn create =
        LOAD_FN(api, "SteamInternal_CreateInterface", CreateInterfaceFn);
    SteamClientFn legacy_client =
        LOAD_FN(api, "SteamClient", SteamClientFn);
    if (!init || !run_callbacks || !shutdown || !get_pipe || !get_user ||
        (!create && !legacy_client)) {
        return 2;
    }

    if (check_restart && restart)
        printf("restart_app=%u\n", (unsigned)restart((uint32_t)expected));
    if (check_running && is_running)
        printf("steam_running=%u\n", (unsigned)is_running());

    printf("steam_api_init_begin=1\n");
    unsigned char initialized = init_with_timeout(init);
    printf("steam_api_init=%u\n", (unsigned)initialized);
    if (!initialized) return 3;

    int pipe = get_pipe();
    int user_handle = get_user();
    printf("steam_pipe=%d\nsteam_user=%d\n", pipe, user_handle);

    void *client = create
        ? interface_with_versions(
              create, client_versions,
              sizeof(client_versions) / sizeof(client_versions[0]))
        : legacy_client();
    if (!create && client)
        printf("interface=SteamClient\n");
    GetUserInterfaceFn get_user_interface =
        LOAD_FN(api, "SteamAPI_ISteamClient_GetISteamUser", GetUserInterfaceFn);
    GetUserInterfaceFn get_apps_interface =
        LOAD_FN(api, "SteamAPI_ISteamClient_GetISteamApps", GetUserInterfaceFn);
    GetUserInterfaceFn get_stats_interface =
        LOAD_FN(api, "SteamAPI_ISteamClient_GetISteamUserStats", GetUserInterfaceFn);
    GetUtilsInterfaceFn get_utils_interface =
        LOAD_FN(api, "SteamAPI_ISteamClient_GetISteamUtils", GetUtilsInterfaceFn);
    if (!client || !get_user_interface || !get_apps_interface ||
        !get_stats_interface || !get_utils_interface) {
        shutdown();
        return 4;
    }

    void *steam_user = user_interface(
        get_user_interface, client, user_handle, pipe, user_versions,
        sizeof(user_versions) / sizeof(user_versions[0]));
    void *steam_apps = user_interface(
        get_apps_interface, client, user_handle, pipe, apps_versions,
        sizeof(apps_versions) / sizeof(apps_versions[0]));
    void *steam_stats = user_interface(
        get_stats_interface, client, user_handle, pipe, stats_versions,
        sizeof(stats_versions) / sizeof(stats_versions[0]));
    void *steam_utils = utils_interface(
        get_utils_interface, client, pipe, utils_versions,
        sizeof(utils_versions) / sizeof(utils_versions[0]));

    UserBoolFn logged_on =
        LOAD_FN(api, "SteamAPI_ISteamUser_BLoggedOn", UserBoolFn);
    UserSteamIdFn get_steam_id =
        LOAD_FN(api, "SteamAPI_ISteamUser_GetSteamID", UserSteamIdFn);
    if (steam_user && logged_on && get_steam_id) {
        printf("steam_logged_on=%d\nsteam_id=%llu\n", logged_on(steam_user),
               (unsigned long long)get_steam_id(steam_user));
    } else {
        printf("steam_user_api=0\n");
    }

    GetAppIdFn get_app_id =
        LOAD_FN(api, "SteamAPI_ISteamUtils_GetAppID", GetAppIdFn);
    UtilsOverlayFn overlay =
        LOAD_FN(api, "SteamAPI_ISteamUtils_IsOverlayEnabled", UtilsOverlayFn);
    uint32_t api_app_id = steam_utils && get_app_id ? get_app_id(steam_utils) : 0;
    printf("steam_app_id=%u\n", api_app_id);
    if (expected && api_app_id != (uint32_t)expected) {
        printf("steam_app_id_match=0\n");
    } else {
        printf("steam_app_id_match=%d\n", expected ? 1 : -1);
    }
    printf("overlay_enabled=%d\n",
           steam_utils && overlay ? overlay(steam_utils) : -1);

    AppsBoolFn subscribed =
        LOAD_FN(api, "SteamAPI_ISteamApps_BIsSubscribed", AppsBoolFn);
    AppsBoolAppFn subscribed_app =
        LOAD_FN(api, "SteamAPI_ISteamApps_BIsSubscribedApp", AppsBoolAppFn);
    AppsBoolAppFn dlc_installed =
        LOAD_FN(api, "SteamAPI_ISteamApps_BIsDlcInstalled", AppsBoolAppFn);
    AppsCountFn dlc_count =
        LOAD_FN(api, "SteamAPI_ISteamApps_GetDLCCount", AppsCountFn);
    AppsDlcFn dlc_data =
        LOAD_FN(api, "SteamAPI_ISteamApps_BGetDLCDataByIndex", AppsDlcFn);
    if (steam_apps && subscribed && subscribed_app && dlc_installed &&
        dlc_count && dlc_data && api_app_id) {
        printf("subscribed=%d\nsubscribed_app=%d\n", subscribed(steam_apps),
               subscribed_app(steam_apps, api_app_id));
        int count = dlc_count(steam_apps, api_app_id);
        printf("dlc_count=%d\n", count);
        for (int i = 0; i < count && i < 64; ++i) {
            uint32_t dlc_id = 0;
            int available = 0;
            char name[256] = {0};
            int ok = dlc_data(steam_apps, api_app_id, i, &dlc_id, &available,
                              name, (int)sizeof(name));
            printf("dlc[%d]=ok:%d,id:%u,available:%d,installed:%d,name:%s\n",
                   i, ok, dlc_id, available, ok ? dlc_installed(steam_apps, dlc_id) : 0,
                   ok ? name : "");
        }
    } else {
        printf("apps_api=0\n");
    }

    StatsRequestFn request_stats = LOAD_FN(
        api, "SteamAPI_ISteamUserStats_RequestCurrentStats", StatsRequestFn);
    StatsCountFn achievement_count = LOAD_FN(
        api, "SteamAPI_ISteamUserStats_GetNumAchievements", StatsCountFn);
    StatsNameFn achievement_name = LOAD_FN(
        api, "SteamAPI_ISteamUserStats_GetAchievementName", StatsNameFn);
    StatsAchievementFn get_achievement = LOAD_FN(
        api, "SteamAPI_ISteamUserStats_GetAchievement", StatsAchievementFn);
    if (steam_stats && request_stats && achievement_count && achievement_name &&
        get_achievement) {
        printf("request_current_stats=%d\n", request_stats(steam_stats));
        for (int i = 0; i < 20; ++i) {
            run_callbacks();
            Sleep(100);
        }
        int count = achievement_count(steam_stats);
        printf("achievement_count=%d\n", count);
        if (count > 0) {
            const char *name = achievement_name(steam_stats, 0);
            int achieved = 0;
            printf("achievement[0]=name:%s,achieved:%d\n", name ? name : "",
                   name ? get_achievement(steam_stats, name, &achieved) : 0);
            printf("achievement[0]_state=%d\n", achieved);
        }
    } else {
        printf("stats_api=0\n");
    }

    shutdown();
    printf("steam_api_shutdown=1\n");
    return 0;
}

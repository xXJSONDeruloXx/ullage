/*
 * In-process native Steam session bootstrap for the macOS Wine boundary.
 *
 * This is intentionally a small inserted dylib rather than a second Steam
 * client.  It loads the user's already-installed native steamclient.dylib,
 * creates a normal native pipe, selects the most-recent cached account from
 * Steam's loginusers.vdf, and asks the native client engine to log that
 * account on.  The pipe/user are held for the lifetime of the Wine process so
 * the later Wine-side lsteamclient calls share the same native client
 * process/service state.
 *
 * No refresh token, password, GameHub Agent, patched executable, or synthetic
 * ticket is accepted or generated here.  If the cached account cannot be
 * resolved, the dylib logs a bounded diagnostic and leaves the normal
 * lsteamclient path untouched.
 */

#define _DARWIN_C_SOURCE

#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

typedef void *(*create_interface_fn)(const char *, int *);
typedef int (*create_global_user_fn)(int *);
typedef int (*logged_on_fn)(int, int);
typedef int (*get_callback_fn)(int, void *);
typedef void (*free_callback_fn)(int);
typedef void (*release_user_fn)(int, int);
typedef int (*release_pipe_fn)(int);

typedef void *(*engine_get_user_fn)(void *, int, int, const char *);
typedef int (*user_account_known_fn)(void *, const char *);
typedef int (*user_set_account_fn)(void *, const char *, int);
typedef int (*user_logon_fn)(void *, uint64_t);

static void *native_steam;
static int native_pipe;
static int native_user;
static logged_on_fn native_logged_on;
static get_callback_fn native_get_callback;
static free_callback_fn native_free_callback;
static release_user_fn native_release_user;
static release_pipe_fn native_release_pipe;

static void session_log(const char *message)
{
    fprintf(stderr, "[ullage-native-steam-session] %s\n", message);
}

static int copy_quoted(const char **cursor, char *value, size_t capacity)
{
    const char *start;
    const char *end;
    size_t length;

    while (**cursor && **cursor != '"')
        ++*cursor;
    if (!**cursor)
        return 0;
    start = ++*cursor;
    end = strchr(start, '"');
    if (!end)
        return 0;
    length = (size_t)(end - start);
    if (!capacity || length >= capacity)
        return 0;
    memcpy(value, start, length);
    value[length] = '\0';
    *cursor = end + 1;
    return 1;
}

static int numeric_steam_id(const char *value, uint64_t *result)
{
    char *end = NULL;
    unsigned long long parsed;

    if (!value || !*value)
        return 0;
    parsed = strtoull(value, &end, 10);
    if (end == value || *end || parsed == 0)
        return 0;
    *result = (uint64_t)parsed;
    return 1;
}

static int resolve_cached_account(const char *steam_root, char *account,
        size_t account_capacity, uint64_t *steam_id)
{
    char path[4096];
    FILE *stream;
    char line[1024];
    char current_id[64] = "";
    char current_account[256] = "";
    char selected_id[64] = "";
    char selected_account[256] = "";

    if (!steam_root || !*steam_root || !account || !account_capacity || !steam_id)
        return 0;
    if (snprintf(path, sizeof(path), "%s/config/loginusers.vdf", steam_root)
            >= (int)sizeof(path))
        return 0;
    stream = fopen(path, "r");
    if (!stream)
        return 0;

    while (fgets(line, sizeof(line), stream))
    {
        const char *cursor = line;
        char key[256];
        char value[256];
        int has_value;

        if (!copy_quoted(&cursor, key, sizeof(key)))
            continue;
        has_value = copy_quoted(&cursor, value, sizeof(value));

        if (!has_value && numeric_steam_id(key, steam_id))
        {
            (void)snprintf(current_id, sizeof(current_id), "%s", key);
            current_account[0] = '\0';
            continue;
        }
        if (!strcmp(key, "AccountName") && has_value)
        {
            (void)snprintf(current_account, sizeof(current_account), "%s", value);
            continue;
        }
        if (!strcmp(key, "MostRecent") && has_value && !strcmp(value, "1") &&
            current_id[0] && current_account[0])
        {
            (void)snprintf(selected_id, sizeof(selected_id), "%s", current_id);
            (void)snprintf(selected_account, sizeof(selected_account), "%s",
                    current_account);
        }
        if (!strcmp(key, "AutoLogin") && has_value && !strcmp(value, "1") &&
            current_id[0] && current_account[0])
        {
            (void)snprintf(selected_id, sizeof(selected_id), "%s", current_id);
            (void)snprintf(selected_account, sizeof(selected_account), "%s",
                    current_account);
        }
    }
    fclose(stream);

    if (!selected_id[0] && current_id[0] && current_account[0])
    {
        (void)snprintf(selected_id, sizeof(selected_id), "%s", current_id);
        (void)snprintf(selected_account, sizeof(selected_account), "%s",
                current_account);
    }
    if (selected_id[0] && selected_account[0])
    {
        if (!numeric_steam_id(selected_id, steam_id))
            return 0;
        (void)snprintf(account, account_capacity, "%s", selected_account);
        return 1;
    }
    return 0;
}

static int resolve_function(void **target, const char *name)
{
    *target = dlsym(native_steam, name);
    return *target != NULL;
}

static void release_native_session(void)
{
    if (native_release_user && native_pipe && native_user)
        native_release_user(native_pipe, native_user);
    if (native_release_pipe && native_pipe)
        (void)native_release_pipe(native_pipe);
    native_pipe = 0;
    native_user = 0;
}

static void initialize_native_session(void)
{
    const char *steam_root = getenv("SteamPath");
    const char *install_path = getenv("STEAM_COMPAT_CLIENT_INSTALL_PATH");
    char path[4096];
    char account[256];
    uint64_t steam_id = 0;
    create_interface_fn create_interface;
    create_global_user_fn create_global_user;
    int return_code = 0;
    void *engine;
    void *engine_user;
    void **engine_vtable;
    void **user_vtable;

    /*
     * DYLD_INSERT_LIBRARIES is inherited by every Wine-side helper and game
     * process.  The native pipe belongs to the first process in this tree;
     * descendants must reuse the Steam transport instead of creating their
     * own native sessions.
     */
    if (getenv("ULLAGE_NATIVE_SESSION_OWNER"))
        return;

    if (!steam_root || !*steam_root || !install_path || !*install_path)
    {
        session_log("missing SteamPath or native client install path; skipped");
        return;
    }
    if (snprintf(path, sizeof(path), "%s/steamclient.dylib", install_path)
            >= (int)sizeof(path))
    {
        session_log("native client path is too long; skipped");
        return;
    }
    if (!resolve_cached_account(steam_root, account, sizeof(account), &steam_id))
    {
        session_log("no most-recent cached Steam account was found; skipped");
        return;
    }
    if (setenv("ULLAGE_NATIVE_SESSION_OWNER", "1", 1) != 0)
    {
        session_log("could not mark the native session owner; skipped");
        return;
    }

    native_steam = dlopen(path, RTLD_NOW | RTLD_LOCAL);
    if (!native_steam)
    {
        session_log("native steamclient.dylib could not be loaded; skipped");
        return;
    }
    if (!resolve_function((void **)&create_interface, "CreateInterface") ||
        !resolve_function((void **)&create_global_user, "Steam_CreateGlobalUser") ||
        !resolve_function((void **)&native_logged_on, "Steam_BLoggedOn") ||
        !resolve_function((void **)&native_get_callback, "Steam_BGetCallback") ||
        !resolve_function((void **)&native_free_callback, "Steam_FreeLastCallback") ||
        !resolve_function((void **)&native_release_user, "Steam_ReleaseUser") ||
        !resolve_function((void **)&native_release_pipe, "Steam_BReleaseSteamPipe"))
    {
        session_log("native client session exports are incomplete; skipped");
        return;
    }

    native_user = create_global_user(&native_pipe);
    if (!native_pipe || !native_user)
    {
        session_log("native Steam pipe/user creation failed; skipped");
        release_native_session();
        return;
    }

    engine = create_interface("CLIENTENGINE_INTERFACE_VERSION005", &return_code);
    if (!engine || return_code)
    {
        session_log("native client engine interface is unavailable; skipped");
        release_native_session();
        return;
    }
    engine_vtable = *(void ***)engine;
    engine_user = ((engine_get_user_fn)engine_vtable[8])(
            engine, native_user, native_pipe, "CLIENTUSER_INTERFACE_VERSION001");
    if (!engine_user)
    {
        session_log("native client user interface is unavailable; skipped");
        release_native_session();
        return;
    }
    user_vtable = *(void ***)engine_user;
    if (!((user_account_known_fn)user_vtable[49])(engine_user, account))
    {
        session_log("cached account is not known to the native client; skipped");
        release_native_session();
        return;
    }
    if (!((user_set_account_fn)user_vtable[50])(engine_user, account, 1))
    {
        session_log("native client rejected the cached account selection; skipped");
        release_native_session();
        return;
    }
    (void)((user_logon_fn)user_vtable[1])(engine_user, steam_id);

    for (int tick = 0; tick < 150; ++tick)
    {
        char callback[128];

        while (native_get_callback(native_pipe, callback))
            native_free_callback(native_pipe);
        if (native_logged_on(native_pipe, native_user))
        {
            session_log("cached native Steam session is logged on and held for Wine");
            return;
        }
        usleep(100 * 1000);
    }
    session_log("cached native Steam session did not reach logged-on state; skipped");
    release_native_session();
}

__attribute__((constructor))
static void ullage_native_steam_session_constructor(void)
{
    initialize_native_session();
}

__attribute__((destructor))
static void ullage_native_steam_session_destructor(void)
{
    release_native_session();
}

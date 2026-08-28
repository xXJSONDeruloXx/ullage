/*
 * Bounded session-capability probe for Valve's native Steam client on macOS.
 *
 * Unlike ullage-native-steamclient-probe.c, this deliberately exercises only
 * the public pipe/user lifecycle plus private-interface discovery. It never
 * requests a login token, prints account data, invokes login or launch
 * methods, launches an app, or creates Windows DRM objects. The child is
 * killed if the client does not return in the bounded interval so a loader
 * experiment cannot strand the host.
 */

#define _DARWIN_C_SOURCE

#include <dlfcn.h>
#include <errno.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

typedef void *(*create_interface_fn)(const char *, int *);
typedef int (*create_global_user_fn)(int *);
typedef int (*create_steam_pipe_fn)(void);
typedef int (*logged_on_fn)(int, int);
typedef int (*get_callback_fn)(int, void *);
typedef void (*free_callback_fn)(int);
typedef void (*release_user_fn)(int, int);
typedef int (*release_pipe_fn)(int);

typedef int (*client_create_pipe_method_fn)(void *);
typedef int (*client_connect_global_user_method_fn)(void *, int);
typedef int (*client_release_user_method_fn)(void *, int, int);
typedef int (*client_release_pipe_method_fn)(void *, int);
typedef void *(*client_get_user_method_fn)(void *, int, int, const char *);
typedef int (*user_logged_on_method_fn)(void *);
typedef void *(*engine_get_user_method_fn)(void *, int, int, const char *);
typedef int (*user_account_logged_in_method_fn)(void *, const char *);

static void print_vtable_summary(const char *name, void *object)
{
    void **vtable;

    if (!object)
    {
        printf("interface=%s pointer=null\n", name);
        return;
    }

    vtable = *(void ***)object;
    printf("interface=%s pointer=present vtable=%p slot0=%p slot8=%p slot43=%p\n",
            name, (void *)vtable,
            vtable ? vtable[0] : NULL,
            vtable ? vtable[8] : NULL,
            vtable ? vtable[43] : NULL);
}

static int run_probe(const char *path)
{
    void *handle;
    create_interface_fn create_interface;
    create_global_user_fn create_global_user;
    create_steam_pipe_fn create_steam_pipe;
    logged_on_fn logged_on;
    get_callback_fn get_callback;
    free_callback_fn free_callback;
    release_user_fn release_user;
    release_pipe_fn release_pipe;
    int rc = -1;
    int pipe = 0;
    int user = 0;
    int logged = 0;
    int callbacks = 0;
    char callback[64];
    void *engine = NULL;

    setvbuf(stdout, NULL, _IONBF, 0);

    /* These are routing hints only; no session state is copied or changed. */
    setenv("SteamAppId", "2492670", 1);
    setenv("SteamGameId", "2492670", 1);
    setenv("SteamClientLaunch", "1", 1);

    handle = dlopen(path, RTLD_NOW | RTLD_LOCAL);
    if (!handle)
    {
        printf("dlopen=failed\n");
        return 2;
    }

    *(void **)(&create_interface) = dlsym(handle, "CreateInterface");
    *(void **)(&create_global_user) = dlsym(handle, "Steam_CreateGlobalUser");
    *(void **)(&create_steam_pipe) = dlsym(handle, "Steam_CreateSteamPipe");
    *(void **)(&logged_on) = dlsym(handle, "Steam_BLoggedOn");
    *(void **)(&get_callback) = dlsym(handle, "Steam_BGetCallback");
    *(void **)(&free_callback) = dlsym(handle, "Steam_FreeLastCallback");
    *(void **)(&release_user) = dlsym(handle, "Steam_ReleaseUser");
    *(void **)(&release_pipe) = dlsym(handle, "Steam_BReleaseSteamPipe");

    printf("exports create_interface=%s global_user=%s steam_pipe=%s "
           "logged_on=%s callbacks=%s release_user=%s release_pipe=%s\n",
            create_interface ? "present" : "null",
            create_global_user ? "present" : "null",
            create_steam_pipe ? "present" : "null",
            logged_on ? "present" : "null",
            get_callback && free_callback ? "present" : "null",
            release_user ? "present" : "null",
            release_pipe ? "present" : "null");

    if (create_interface)
    {
        engine = create_interface("CLIENTENGINE_INTERFACE_VERSION005", &rc);
        printf("create_interface=CLIENTENGINE_INTERFACE_VERSION005 rc=%d\n", rc);
        print_vtable_summary("CLIENTENGINE_INTERFACE_VERSION005", engine);
    }

    /* Exercise the public SteamClient pipe path separately from the flat
     * CreateGlobalUser path below.  This is still ordinary Steamworks
     * lifecycle, not the private app-launch interface. */
    if (create_interface)
    {
        void *client = create_interface("SteamClient023", &rc);
        printf("create_interface=SteamClient023 rc=%d\n", rc);
        if (client && rc == 0)
        {
            void **client_vtable = *(void ***)client;
            client_create_pipe_method_fn create_pipe =
                (client_create_pipe_method_fn)client_vtable[0];
            client_connect_global_user_method_fn connect_global_user =
                (client_connect_global_user_method_fn)client_vtable[2];
            client_release_user_method_fn release_public_user =
                (client_release_user_method_fn)client_vtable[4];
            client_get_user_method_fn get_public_user =
                (client_get_user_method_fn)client_vtable[5];
            client_release_pipe_method_fn release_public_pipe =
                (client_release_pipe_method_fn)client_vtable[1];
            int public_pipe = create_pipe(client);
            int public_user = public_pipe ?
                connect_global_user(client, public_pipe) : 0;

            printf("public_pipe pipe=%d user=%d\n", public_pipe, public_user);
            if (public_pipe && public_user)
            {
                void *public_user_iface = get_public_user(
                    client, public_user, public_pipe, "SteamUser023");
                int public_logged = 0;
                if (public_user_iface)
                {
                    void **user_vtable = *(void ***)public_user_iface;
                    user_logged_on_method_fn user_logged_on =
                        (user_logged_on_method_fn)user_vtable[1];
                    public_logged = user_logged_on(public_user_iface) ? 1 : 0;
                }
                printf("public_session logged_on=%d\n", public_logged);
                release_public_user(client, public_pipe, public_user);
            }
            if (public_pipe)
                (void)release_public_pipe(client, public_pipe);
            printf("public_session released=1\n");
        }
    }

    /* This is the same public lifecycle used by a Steamworks client. */
    if (create_global_user)
    {
        user = create_global_user(&pipe);
        printf("global_user pipe=%d user=%d\n", pipe, user);
    }

    if (!user || !pipe)
    {
        /* Steam_CreateSteamPipe is reported for comparison only; do not leave
         * a pipe open if a client implementation returned one unexpectedly. */
        if (create_steam_pipe)
        {
            int legacy_pipe = create_steam_pipe();
            printf("steam_pipe legacy_result=%d\n", legacy_pipe);
            if (legacy_pipe && release_pipe)
                (void)release_pipe(legacy_pipe);
        }
        return 3;
    }

    if (engine)
    {
        void **engine_vtable = *(void ***)engine;
        engine_get_user_method_fn get_engine_user =
            (engine_get_user_method_fn)engine_vtable[8];
        void *engine_user = get_engine_user(
            engine, user, pipe, "CLIENTUSER_INTERFACE_VERSION001");
        printf("engine_user pointer=%s\n", engine_user ? "present" : "null");
        if (engine_user)
        {
            void **user_vtable = *(void ***)engine_user;
            printf("engine_user_vtable slot1=%p slot4=%p slot49=%p "
                   "slot54=%p slot56=%p\n",
                    user_vtable[1], user_vtable[4], user_vtable[49],
                    user_vtable[54], user_vtable[56]);
            if (getenv("ULLAGE_STEAM_ACCOUNT") &&
                *getenv("ULLAGE_STEAM_ACCOUNT"))
            {
                user_account_logged_in_method_fn account_logged_in =
                    (user_account_logged_in_method_fn)user_vtable[49];
                int account_known = account_logged_in(
                    engine_user, getenv("ULLAGE_STEAM_ACCOUNT")) ? 1 : 0;
                printf("engine_user account_logged_in=%d\n", account_known);
            }
        }
    }

    for (int tick = 0; tick < 20; ++tick)
    {
        memset(callback, 0, sizeof(callback));
        if (get_callback && free_callback)
        {
            while (get_callback(pipe, callback))
            {
                ++callbacks;
                free_callback(pipe);
            }
        }
        if (logged_on)
            logged = logged_on(pipe, user) ? 1 : 0;
        if (logged)
            break;
        usleep(100 * 1000);
    }
    printf("session logged_on=%d callbacks=%d\n", logged, callbacks);

    if (release_user)
        release_user(pipe, user);
    if (release_pipe)
        (void)release_pipe(pipe);
    printf("session released=1\n");
    return logged ? 0 : 4;
}

int main(int argc, char **argv)
{
    pid_t pid;
    int status = 0;
    time_t deadline;

    if (argc != 2)
    {
        fprintf(stderr, "usage: %s /path/to/steamclient.dylib\n", argv[0]);
        return 2;
    }

    pid = fork();
    if (pid < 0)
    {
        perror("fork");
        return 2;
    }
    if (!pid)
        _exit(run_probe(argv[1]));

    deadline = time(NULL) + 8;
    for (;;)
    {
        pid_t waited = waitpid(pid, &status, WNOHANG);
        if (waited == pid)
            break;
        if (waited < 0 && errno != EINTR)
        {
            perror("waitpid");
            return 2;
        }
        if (time(NULL) >= deadline)
        {
            (void)kill(pid, SIGKILL);
            (void)waitpid(pid, &status, 0);
            printf("probe_timeout=1\n");
            return 124;
        }
        usleep(50 * 1000);
    }

    if (WIFEXITED(status))
    {
        printf("child_status=%d\n", WEXITSTATUS(status));
        return WEXITSTATUS(status);
    }
    if (WIFSIGNALED(status))
    {
        printf("child_signal=%d\n", WTERMSIG(status));
        return 128 + WTERMSIG(status);
    }
    return 2;
}

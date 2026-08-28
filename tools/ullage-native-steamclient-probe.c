/*
 * Read-only capability probe for the native Steam client on macOS.
 *
 * This deliberately calls only CreateInterface and never invokes a returned
 * vtable.  Each query runs in a child so a private/unsupported interface
 * cannot take down the parent probe.  Do not use this as a game launcher or
 * as a substitute for an authenticated Steam session.
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
#include <unistd.h>

typedef void *(*create_interface_fn)(const char *, int *);

struct query_result
{
    uintptr_t interface_ptr;
    int return_code;
};

static int query_interface(const char *path, const char *name,
        struct query_result *result)
{
    int pipe_fds[2];
    pid_t pid;
    int status;

    if (pipe(pipe_fds) < 0)
    {
        fprintf(stderr, "pipe(%s): %s\n", name, strerror(errno));
        return -1;
    }

    pid = fork();
    if (pid < 0)
    {
        fprintf(stderr, "fork(%s): %s\n", name, strerror(errno));
        close(pipe_fds[0]);
        close(pipe_fds[1]);
        return -1;
    }

    if (!pid)
    {
        void *handle;
        create_interface_fn create_interface;
        struct query_result child_result = {0};
        ssize_t written;

        close(pipe_fds[0]);
        handle = dlopen(path, RTLD_NOW | RTLD_LOCAL);
        if (handle)
        {
            *(void **)(&create_interface) = dlsym(handle, "CreateInterface");
            if (create_interface)
                child_result.interface_ptr = (uintptr_t)create_interface(name,
                        &child_result.return_code);
        }

        written = write(pipe_fds[1], &child_result, sizeof(child_result));
        close(pipe_fds[1]);
        _exit(written == (ssize_t)sizeof(child_result) ? 0 : 1);
    }

    close(pipe_fds[1]);
    memset(result, 0, sizeof(*result));
    if (read(pipe_fds[0], result, sizeof(*result)) != (ssize_t)sizeof(*result))
        memset(result, 0, sizeof(*result));
    close(pipe_fds[0]);

    while (waitpid(pid, &status, 0) < 0)
        if (errno != EINTR)
            break;

    if (WIFEXITED(status))
        return WEXITSTATUS(status);
    if (WIFSIGNALED(status))
        return 128 + WTERMSIG(status);
    return -1;
}

int main(int argc, char **argv)
{
    static const char *const default_names[] = {
        "SteamClient015", "SteamClient016", "SteamClient017",
        "SteamClient018", "SteamClient019", "SteamClient020",
        "SteamClient021", "SteamClient022", "SteamClient023",
        "CLIENTENGINE_INTERFACE_VERSION004",
        "CLIENTENGINE_INTERFACE_VERSION005",
    };
    const char *path;
    size_t i;

    if (argc != 2)
    {
        fprintf(stderr, "usage: %s /path/to/steamclient.dylib\n", argv[0]);
        return 2;
    }
    path = argv[1];

    for (i = 0; i < sizeof(default_names) / sizeof(default_names[0]); i++)
    {
        struct query_result result;
        int child_status = query_interface(path, default_names[i], &result);

        printf("interface=%s child_status=%d pointer=%s return_code=%d\n",
                default_names[i], child_status,
                result.interface_ptr ? "present" : "null",
                result.return_code);
    }
    return 0;
}

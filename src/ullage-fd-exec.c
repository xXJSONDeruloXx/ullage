/*
 * Replace the current process after closing inherited descriptors >= 3.
 * Native Steam keeps control/IPC descriptors open in the child it starts;
 * Wine games otherwise inherit those descriptors and can misinterpret them
 * as Steam or graphics handles. Keeping stdin/stdout/stderr is deliberate:
 * the caller redirects them to the per-game log.
 */
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>
#include <sys/resource.h>
#include <unistd.h>

static void close_inherited_fds(void)
{
    struct rlimit limit;
    int upper = 65536;
    long open_max = sysconf(_SC_OPEN_MAX);

    if (open_max > 0 && open_max < INT_MAX)
        upper = (int)open_max;

    if (getrlimit(RLIMIT_NOFILE, &limit) == 0 && limit.rlim_cur < (rlim_t)upper)
        upper = (int)limit.rlim_cur;

    for (int fd = 3; fd < upper; ++fd)
        (void)close(fd);
}

int main(int argc, char **argv)
{
    int program_index = 1;

    if (argc > 1 && strcmp(argv[1], "--preserve-fds") == 0)
        program_index = 2;

    if (argc <= program_index) {
        fprintf(stderr, "usage: %s [--preserve-fds] PROGRAM [ARGUMENT...]\n", argv[0]);
        return 2;
    }

    if (program_index == 1)
        close_inherited_fds();
    execvp(argv[program_index], &argv[program_index]);

    fprintf(stderr, "%s: %s: %s\n", argv[0], argv[program_index], strerror(errno));
    return 127;
}

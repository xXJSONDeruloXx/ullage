/*
 * Experimental SteamStart shared-memory service for controlled diagnostics.
 *
 * The Windows Steam client creates a 1 KiB mapping and an auto-reset named
 * event.  A protected launcher writes its PID and an event handle into the
 * mapping, then waits for the client to duplicate and signal that handle.  This
 * helper reproduces only that OS-level handoff so the launch boundary can be
 * tested without changing a game executable or loading third-party DRM code.
 * It does not implement Steam authentication, licensing, or the client DRM
 * backend, and is not enabled by the normal Ullage launch path.
 */

#define WIN32_LEAN_AND_MEAN

#include <windows.h>

#include <stdint.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

enum {
    kMappingSize = 0x400,
    kFieldVersion = 0x90,
    kFieldState = 0x94,
    kFieldLauncherPid = 0x98,
    kFieldLauncherEvent = 0xa0,
    kFieldAppId = 0xa8,
    kFieldAc = 0xac,
    kFieldStatus = 0xb0,
    kFieldB4 = 0xb4,
};

static FILE *server_log_file;

static void server_log(const char *format, ...) {
    va_list args;
    va_start(args, format);
    vfprintf(stdout, format, args);
    va_end(args);

    if (!server_log_file)
        server_log_file = fopen("ullage-steamstart-server.log", "a");
    if (!server_log_file) return;
    va_start(args, format);
    vfprintf(server_log_file, format, args);
    va_end(args);
    fflush(server_log_file);
}

static uint32_t read_u32(const unsigned char *view, size_t offset) {
    uint32_t value = 0;
    memcpy(&value, view + offset, sizeof(value));
    return value;
}

static uintptr_t read_ptr(const unsigned char *view, size_t offset) {
    uintptr_t value = 0;
    memcpy(&value, view + offset, sizeof(value));
    return value;
}

static void write_u32(unsigned char *view, size_t offset, uint32_t value) {
    memcpy(view + offset, &value, sizeof(value));
}

static int initialize_security(SECURITY_DESCRIPTOR *descriptor,
                               SECURITY_ATTRIBUTES *attributes) {
    if (!InitializeSecurityDescriptor(descriptor, SECURITY_DESCRIPTOR_REVISION)) {
        server_log("InitializeSecurityDescriptor failed error=%lu\n",
                   (unsigned long)GetLastError());
        return 0;
    }
    if (!SetSecurityDescriptorDacl(descriptor, TRUE, NULL, FALSE)) {
        server_log("SetSecurityDescriptorDacl failed error=%lu\n",
                   (unsigned long)GetLastError());
        return 0;
    }
    attributes->nLength = sizeof(*attributes);
    attributes->lpSecurityDescriptor = descriptor;
    attributes->bInheritHandle = FALSE;
    return 1;
}

static void reset_request(unsigned char *view, HANDLE lock) {
    write_u32(view, kFieldVersion, 2);
    write_u32(view, kFieldState, 0);
    write_u32(view, kFieldLauncherPid, 0);
    write_u32(view, kFieldAppId, 0);
    SetEvent(lock);
}

int main(void) {
    setbuf(stdout, NULL);
    setbuf(stderr, NULL);
    server_log("steamstart_server_begin\n");

    SECURITY_DESCRIPTOR descriptor;
    SECURITY_ATTRIBUTES attributes;
    if (!initialize_security(&descriptor, &attributes)) return 2;

    HANDLE mapping = CreateFileMappingA(INVALID_HANDLE_VALUE, &attributes,
                                        PAGE_READWRITE, 0, kMappingSize,
                                        "Local\\SteamStart_SharedMemFile");
    if (!mapping) {
        server_log("CreateFileMapping failed error=%lu\n",
                   (unsigned long)GetLastError());
        return 3;
    }

    unsigned char *view = (unsigned char *)MapViewOfFile(
        mapping, FILE_MAP_ALL_ACCESS, 0, 0, kMappingSize);
    if (!view) {
        server_log("MapViewOfFile failed error=%lu\n",
                   (unsigned long)GetLastError());
        CloseHandle(mapping);
        return 4;
    }

    HANDLE lock = CreateEventA(&attributes, FALSE, FALSE,
                               "Local\\SteamStart_SharedMemLock");
    if (!lock) {
        server_log("CreateEvent failed error=%lu\n",
                   (unsigned long)GetLastError());
        UnmapViewOfFile(view);
        CloseHandle(mapping);
        return 5;
    }

    reset_request(view, lock);
    server_log("steamstart_server_ready version=%u state=%u mapping=%p lock=%p\n",
               read_u32(view, kFieldVersion), read_u32(view, kFieldState),
               mapping, lock);

    DWORD last_state = 0;
    for (int iteration = 0; iteration < 12000; ++iteration) {
        DWORD state = read_u32(view, kFieldState);
        if (state == 2 && last_state != 2) {
            DWORD launcher_pid = read_u32(view, kFieldLauncherPid);
            uintptr_t raw_event = read_ptr(view, kFieldLauncherEvent);
            server_log("steamstart_request pid=%lu event=%p appid=%u ac=%u "
                       "status=%u b4=%u\n",
                       (unsigned long)launcher_pid, (void *)raw_event,
                       read_u32(view, kFieldAppId), read_u32(view, kFieldAc),
                       read_u32(view, kFieldStatus), read_u32(view, kFieldB4));

            HANDLE launcher = OpenProcess(0x001F0FFF, FALSE, launcher_pid);
            HANDLE response_event = NULL;
            BOOL duplicated = FALSE;
            if (launcher && raw_event != 0) {
                duplicated = DuplicateHandle(
                    launcher, (HANDLE)raw_event, GetCurrentProcess(),
                    &response_event, 0x001F0003, FALSE, 0);
            }
            if (!duplicated) {
                server_log("steamstart_duplicate=0 error=%lu\n",
                           (unsigned long)GetLastError());
            } else {
                BOOL signaled = SetEvent(response_event);
                server_log("steamstart_duplicate=1 signal=%u error=%lu\n",
                           signaled ? 1U : 0U,
                           signaled ? 0UL : (unsigned long)GetLastError());
                CloseHandle(response_event);
            }
            if (launcher) CloseHandle(launcher);

            reset_request(view, lock);
            server_log("steamstart_request_complete state=%u\n",
                       read_u32(view, kFieldState));
            last_state = 0;
        } else {
            last_state = state;
        }
        Sleep(5);
    }

    CloseHandle(lock);
    UnmapViewOfFile(view);
    CloseHandle(mapping);
    server_log("steamstart_server_exit\n");
    return 0;
}

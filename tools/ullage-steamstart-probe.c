/*
 * Read-only probe for the legacy Steam DRM startup handshake.
 *
 * Some Windows Steam depots open these named objects before their real
 * launcher starts.  This probe only opens and reads the objects; it never
 * writes the mapping, signals an event, or alters the target depot.
 */

#include <windows.h>

#include <stdint.h>
#include <stdio.h>
#include <string.h>

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

int main(void) {
    HANDLE lock = OpenEventA(SYNCHRONIZE, FALSE,
                             "Local\\SteamStart_SharedMemLock");
    printf("lock_open=%u lock=%p error=%lu\n", lock != NULL, lock,
           lock ? 0UL : (unsigned long)GetLastError());

    HANDLE mapping = OpenFileMappingA(FILE_MAP_READ, FALSE,
                                      "Local\\SteamStart_SharedMemFile");
    printf("mapping_open=%u mapping=%p error=%lu\n", mapping != NULL, mapping,
           mapping ? 0UL : (unsigned long)GetLastError());
    if (!mapping) {
        if (lock) CloseHandle(lock);
        return 1;
    }

    unsigned char *view = MapViewOfFile(mapping, FILE_MAP_READ, 0, 0, 0x400);
    printf("view_open=%u view=%p error=%lu\n", view != NULL, view,
           view ? 0UL : (unsigned long)GetLastError());
    if (!view) {
        CloseHandle(mapping);
        if (lock) CloseHandle(lock);
        return 2;
    }

    printf("version=%u state=%u launcher_pid=%u launcher_event=%p\n",
           read_u32(view, 0x90), read_u32(view, 0x94),
           read_u32(view, 0x98), (void *)read_ptr(view, 0xa0));
    printf("appid=%u field_ac=%u status=%u field_b4=%u\n",
           read_u32(view, 0xa8), read_u32(view, 0xac), read_u32(view, 0xb0),
           read_u32(view, 0xb4));

    UnmapViewOfFile(view);
    CloseHandle(mapping);
    if (lock) CloseHandle(lock);
    return 0;
}

/* SDK-free arm64 macOS launcher. Uses only public libSystem APIs. */
typedef unsigned int uint32_t;
typedef unsigned long size_t;
extern int _NSGetExecutablePath(char *buffer, uint32_t *size);
extern int execv(const char *path, char *const argv[]);
extern long write(int fd, const void *buffer, size_t count);
extern void _exit(int status);
int main(void) {
    char path[8192];
    uint32_t size = sizeof(path);
    if (_NSGetExecutablePath(path, &size) != 0) _exit(1);
    unsigned int n = 0;
    while (path[n]) n++;
    while (n > 0 && path[n-1] != '/') n--;
    const char suffix[] = "../Resources/launch.sh";
    unsigned int i = 0;
    while ((path[n+i] = suffix[i]) != 0) i++;
    char *args[] = {"/bin/sh", path, (void *)0};
    execv("/bin/sh", args);
    const char error[] = "AHAS could not launch its bundled runtime.\n";
    write(2, error, sizeof(error)-1);
    return 1;
}

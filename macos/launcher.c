/* AHAS native embedding launcher. Keeps the real .app executable/NSBundle identity.
 * Build against the bundled CPython headers; load its exact library by absolute path.
 * No shell/Python exec replacement, system Python, or pip installation is needed.
 */
#include <Python.h>
#include <dlfcn.h>
#include <limits.h>
#include <mach-o/dyld.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

static int failure(const char *message) {
    fprintf(stderr,"AHAS startup error: %s\n",message);
    return 1;
}

int main(void) {
    char executable[PATH_MAX], parent[PATH_MAX], resources[PATH_MAX];
    char temporary[PATH_MAX], python_home[PATH_MAX], library[PATH_MAX], script[PATH_MAX];
    uint32_t size=sizeof(executable);
    if (_NSGetExecutablePath(executable,&size)!=0) return failure("Executable path is too long.");
    if (!realpath(executable,parent)) return failure("Cannot resolve application path.");
    strcpy(executable,parent);
    char *slash=strrchr(parent,'/');
    if (!slash) return failure("Invalid application bundle path.");
    *slash=0;
    snprintf(temporary,sizeof(temporary),"%s/../Resources",parent);
    if (!realpath(temporary,resources)) return failure("App Resources folder is missing.");

    const char *home=getenv("HOME");
    if (home) {
        char logdir[PATH_MAX], logfile[PATH_MAX];
        snprintf(logdir,sizeof(logdir),"%s/Library",home);
        mkdir(logdir,0700);
        snprintf(logdir,sizeof(logdir),"%s/Library/Logs",home);
        mkdir(logdir,0700);
        snprintf(logdir,sizeof(logdir),"%s/Library/Logs/AHAS",home);
        mkdir(logdir,0700);
        snprintf(logfile,sizeof(logfile),"%s/app.log",logdir);
        freopen(logfile,"a",stdout);
        freopen(logfile,"a",stderr);
    }
    setvbuf(stdout,NULL,_IOLBF,0);
    fprintf(stdout,"\n--- AHAS native app · Made by Ahas Nimsandu ---\n");
    snprintf(python_home,sizeof(python_home),"%s/python",resources);
    snprintf(library,sizeof(library),"%s/lib/libpython3.13.dylib",python_home);
    snprintf(script,sizeof(script),"%s/native_host.py",resources);
    void *handle=dlopen(library,RTLD_NOW|RTLD_GLOBAL);
    if (!handle) return failure(dlerror());

    void (*preinit)(PyPreConfig *)=dlsym(handle,"PyPreConfig_InitIsolatedConfig");
    PyStatus (*preinitialize)(const PyPreConfig *)=dlsym(handle,"Py_PreInitialize");
    void (*init)(PyConfig *)=dlsym(handle,"PyConfig_InitIsolatedConfig");
    PyStatus (*set_string)(PyConfig *,wchar_t **,const char *)=dlsym(handle,"PyConfig_SetBytesString");
    PyStatus (*set_argv)(PyConfig *,Py_ssize_t,char *const *)=dlsym(handle,"PyConfig_SetBytesArgv");
    PyStatus (*initialize)(const PyConfig *)=dlsym(handle,"Py_InitializeFromConfig");
    void (*clear)(PyConfig *)=dlsym(handle,"PyConfig_Clear");
    int (*exception)(PyStatus)=dlsym(handle,"PyStatus_Exception");
    int (*run_main)(void)=dlsym(handle,"Py_RunMain");
    if (!preinit||!preinitialize||!init||!set_string||!set_argv||!initialize||!clear||!exception||!run_main)
        return failure("Bundled runtime is missing a required embedding API.");

    PyPreConfig preconfig;
    preinit(&preconfig);
    preconfig.utf8_mode=1;
    PyStatus status=preinitialize(&preconfig);
    if (exception(status)) return failure(status.err_msg ? status.err_msg : "Cannot initialize UTF-8 runtime.");
    PyConfig config;
    init(&config);
    config.parse_argv=0;
    config.write_bytecode=0;
    config.install_signal_handlers=0;
    status=set_string(&config,&config.home,python_home);
    if (!exception(status)) status=set_string(&config,&config.program_name,executable);
    if (!exception(status)) status=set_string(&config,&config.run_filename,script);
    char *args[]={script};
    if (!exception(status)) status=set_argv(&config,1,args);
    if (!exception(status)) status=initialize(&config);
    if (exception(status)) {
        const char *message=status.err_msg ? status.err_msg : "Cannot initialize bundled Python.";
        failure(message);
        clear(&config);
        return 1;
    }
    clear(&config);
    return run_main();
}

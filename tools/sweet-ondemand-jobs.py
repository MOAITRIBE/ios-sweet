#!/usr/bin/env python3
"""Start iOS daemons on demand only, the way HackiOS's userland/mkjobs.py --rest does.

  sweet-ondemand-jobs.py MOUNTED_ROOT [--dry-run]

MOUNTED_ROOT is an iOS root made by tools/mkiosroot-mac.sh + sweet-root-tweaks.py,
mounted read-write. The jobs live in /System/Library/xpc/launchd.plist (read by
launchd when booted with launchd_unsecure_cache=1). Its first state is kept as
launchd.plist.stock next to it and every run starts from that copy, so the script is
idempotent and `cp launchd.plist.stock launchd.plist` undoes it.

Stock iOS starts ~200 daemons at boot (RunAtLoad, KeepAlive, timers, events); on a
CPU-drawn port that is minutes of work before SpringBoard gets the CPU. Here:

  KEEP     jobs that still start at boot: HackiOS's IOS_JOBS (what its lock screen
           needs in ~20 s) plus keybagd (this port's AppleKeyStore path), lockdownd
           and mtmergeprops
  DENY     jobs removed outright: no hardware behind them on the A001, or they crash
           and are asked for again for ever (HackiOS's DENY, minus keybagd, lockdown,
           purplebuddy, datamigrator, which this port's working boots ran with)
  the rest every start trigger removed, so launchd runs a job only when a program
           looks up one of its MachServices; a job without MachServices never runs
           (HackiOS leaves those out of its image)
"""
import os, plistlib, shutil, sys

KEEP = {
    'com.apple.notifyd', 'com.apple.cfprefsd.xpc.daemon', 'com.apple.cfprefsd.xpc.daemon.system',
    'com.apple.logd', 'com.apple.syslogd', 'com.apple.distnoted.xpc.daemon', 'com.apple.diagnosticd',
    'com.apple.fseventsd', 'com.apple.containermanagerd', 'com.apple.containermanagerd.system',
    'com.apple.runningboardd', 'com.apple.backboardd', 'com.apple.mobile.usermanagerd',
    'com.apple.mobilegestalt.xpc', 'com.apple.lsd', 'com.apple.powerd', 'com.apple.analyticsd',
    'com.apple.logd_helper', 'com.apple.iconservices.iconservicesagent', 'com.apple.pluginkit.pkd',
    'com.apple.SpringBoard',
    # not in HackiOS's list: this port's working boots ran with them, and as jobs without
    # MachServices nothing could start them later (mtmergeprops is a one-shot multitouch step)
    'com.apple.mobile.keybagd', 'com.apple.mobile.lockdown', 'com.apple.mtmergeprops',
}

DENY = ('watchdog', 'CommCenter', 'wifi', 'WiFi', 'bluetooth', 'BTServer', 'locationd', 'softwareupdate',
        'backupd', 'thermalmonitord', 'nfcd', 'biometrickitd', 'pearld', 'obliterat', 'storage_mounter',
        'com.apple.fud', 'sepd', 'seputil', 'camera', 'ReportCrash', 'osanalytics', 'audio',
        'jetsamproperties', 'restore', 'usb', 'accessoryd', 'mobileassetd', 'bird',
        'homed', 'routined', 'duetexpertd', 'com.apple.dmd', 'syncdefaultsd', 'photoanalysisd',
        'avconferenced')

TRIGGERS = ('RunAtLoad', 'KeepAlive', 'StartInterval', 'StartCalendarInterval', 'WatchPaths',
            'QueueDirectories', 'StartOnMount', 'LaunchEvents')


def main():
    args = [a for a in sys.argv[1:] if a != '--dry-run']
    dry = '--dry-run' in sys.argv
    if len(args) != 1 or not os.path.isdir(os.path.join(args[0], 'System/Library/xpc')):
        sys.exit(__doc__)
    path = os.path.join(args[0], 'System/Library/xpc/launchd.plist')
    stock = path + '.stock'
    if not os.path.exists(stock) and not dry:
        shutil.copy2(path, stock)
    with open(stock if os.path.exists(stock) else path, 'rb') as f:
        plist = plistlib.load(f)
    jobs = plist['LaunchDaemons']
    kept, denied, demand, never = [], [], [], []
    for key in list(jobs):
        job = jobs[key]
        label = job.get('Label', key)
        if label in KEEP:
            kept.append(label)
        elif any(word in label for word in DENY):
            del jobs[key]
            denied.append(label)
        else:
            started = [t for t in TRIGGERS if t in job]
            for t in started:
                del job[t]
            if not job.get('MachServices'):
                never.append(label)
            elif started:
                demand.append(label)
    missing = KEEP - set(kept)
    if missing:
        print('warning: KEEP jobs not in launchd.plist:', ', '.join(sorted(missing)))
    print(f'launchd.plist: {len(kept)} at boot, {len(demand)} made on-demand, '
          f'{len(never)} without MachServices (never started), {len(denied)} removed')
    for name, group in (('removed', denied), ('never started', never)):
        print(f'  {name}: {" ".join(sorted(group))}')
    if dry:
        return
    st = os.stat(path)
    with open(path, 'wb') as f:
        plistlib.dump(plist, f, fmt=plistlib.FMT_BINARY)
    os.chmod(path, st.st_mode & 0o7777)


if __name__ == '__main__':
    main()

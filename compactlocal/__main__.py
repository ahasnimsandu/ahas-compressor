import argparse
import json
import sys
from .ahas import compress, restore
from .media import optimize


def main():
    if len(sys.argv) < 2 or sys.argv[1].startswith('-'):
        from .server import main as serve
        return serve()
    parser = argparse.ArgumentParser(description='CompactLocal command line')
    sub = parser.add_subparsers(dest='command',required=True)
    c = sub.add_parser('compress')
    c.add_argument('inputs',nargs='+')
    c.add_argument('-o','--output',required=True)
    c.add_argument('--level',type=int,choices=[1,6,9],default=6)
    for name in ('extract','verify'):
        p = sub.add_parser(name)
        p.add_argument('archive')
        p.add_argument('--max-gb',type=float,default=1024,help='Maximum restored size in GiB; default 1024')
        if name == 'extract':
            p.add_argument('-o','--output',required=True)
    m = sub.add_parser('media')
    m.add_argument('inputs',nargs='+')
    m.add_argument('-o','--output',required=True)
    m.add_argument('--profile',choices=['smallest','balanced','quality'],default='balanced')
    m.add_argument('--type',choices=['auto','images','videos'],default='auto')
    m.add_argument('--accept-lossy',action='store_true',required=True)
    args = parser.parse_args()
    try:
        if args.command == 'compress':
            result = compress(args.inputs,args.output,level=args.level)
        elif args.command == 'media':
            result = optimize(args.inputs,args.output,profile=args.profile,media_type=args.type)
        else:
            if not 0 < args.max_gb <= 1048576:
                parser.error('--max-gb must be positive and at most 1048576')
            result = restore(args.archive,getattr(args,'output',None),verify=args.command=='verify',max_bytes=int(args.max_gb*1024**3))
        print(json.dumps(result,indent=2))
    except KeyboardInterrupt:
        print('Cancelled. Incomplete output removed.',file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print('Error: '+str(exc),file=sys.stderr)
        raise SystemExit(1)

if __name__ == '__main__':
    main()

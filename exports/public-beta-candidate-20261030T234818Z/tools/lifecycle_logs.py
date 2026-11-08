"""Render a scoped journald policy to stdout. No installation or log deletion."""
import argparse


def journald_policy(retention_days, max_use_mb):
    if type(retention_days) is not int or not 1<=retention_days<=3650:
        raise ValueError('Explicit approved calendar retention required')
    if type(max_use_mb) is not int or not 16<=max_use_mb<=65536:
        raise ValueError('Explicit disk budget required')
    return ('# Only for journald@documind-lifecycle; never install globally.\n'
            '[Journal]\nStorage=persistent\n'
            f'MaxRetentionSec={retention_days}day\nMaxFileSec=1day\nSystemMaxUse={max_use_mb}M\n'
            '# Capacity rotation may shorten availability; this is a maximum age.\n')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--retention-days',type=int,required=True)
    parser.add_argument('--max-use-mb',type=int,required=True)
    args=parser.parse_args()
    print(journald_policy(args.retention_days,args.max_use_mb),end='')


if __name__=='__main__':main()

"""Structured Gmail notifications; does not replace the existing Sprint 7 Gmail hook."""
import argparse
from email.message import EmailMessage
from email.utils import getaddresses
import json
from pathlib import Path
import re
import shlex
import smtplib
import ssl
import sys

try:
    from .backup_production import private_file
except ImportError:
    from backup_production import private_file

CONFIG = Path('/home/debian/.config/documind-alerts/gmail.env')
KEYS = {'SMTP_HOST', 'SMTP_PORT', 'SMTP_USERNAME', 'SMTP_PASSWORD', 'ALERT_FROM', 'ALERT_TO'}
EVENTS = {
    'disk-warning': 'Espace disque inférieur à 20 Gio : prévoir un nettoyage manuel après revue.',
    'disk-critical': 'Espace disque inférieur à 10 Gio : intervenir rapidement.',
    'disk-emergency': 'Espace disque inférieur à 8 Gio : la prochaine sauvegarde risque d’être bloquée.',
    'backup-missing': 'Aucune sauvegarde automatisée DocuMind valide n’est disponible.',
    'backup-stale': 'La dernière sauvegarde automatisée valide date de plus de 36 heures.',
    'restic-unavailable': 'Impossible de confirmer les sauvegardes Backblaze B2.',
    'backup-timer-failed': 'La planification ou le dernier service de sauvegarde présente une anomalie.',
    'recovery': 'Le contrôle est revenu à la normale.',
    'test-notification': 'Test de notification DocuMind : aucune panne de production n’a été simulée.',
    'documind-backup-failed': 'La sauvegarde DocuMind a échoué : consulter son journal systemd.',
    'retention-failed': 'La simulation de conservation est bloquée ou présente une incohérence. Aucune sauvegarde n’a été supprimée.',
}
REASONS = {
    'repository-unavailable': 'Vérifier l’accès B2 et la configuration privée, sans publier les identifiants.',
    'invalid-response': 'La réponse Restic est invalide ou ne contient pas de sauvegarde automatisée conforme.',
    'timer-missing': 'Le timer de sauvegarde est absent.',
    'timer-disabled': 'Le timer de sauvegarde n’est pas activé.',
    'timer-inactive': 'Le timer de sauvegarde n’est pas actif.',
    'next-run-invalid': 'La prochaine exécution à 03 h Europe/Paris n’est pas confirmée.',
    'service-failed': 'Le dernier service de sauvegarde signale un échec.',
    'service-running-too-long': 'La sauvegarde est en cours depuis plus de quatre heures.',
    'systemd-unavailable': 'Les métadonnées systemd ne sont pas accessibles.',
    'clock-inconsistent': 'L’horloge est incohérente : vérifier la synchronisation du VPS.',
    'normal': 'Aucune action supplémentaire n’est nécessaire pour ce contrôle.',
    'retention-inconsistent': 'Examiner le rapport privé de conservation. Préserver les copies existantes et demander une revue manuelle.',
}


class NotificationError(Exception):
    pass


def smtp_config(path=CONFIG):
    private_file(path)
    values = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        match = re.fullmatch(r'\s*(?:export[ \t]+)?([A-Z][A-Z0-9_]*)=(.*)', line)
        if not match or match[1] not in KEYS or match[1] in values:
            raise NotificationError('invalid_smtp_configuration')
        try:
            tokens = shlex.split(match[2], comments=True, posix=True)
        except ValueError:
            raise NotificationError('invalid_smtp_configuration') from None
        if len(tokens) != 1 or not tokens[0] or any(c in tokens[0] for c in '\r\n\x00`$'):
            raise NotificationError('invalid_smtp_configuration')
        values[match[1]] = tokens[0]
    if set(values) != KEYS or not values['SMTP_PORT'].isdigit() or not 1 <= int(values['SMTP_PORT']) <= 65535:
        raise NotificationError('invalid_smtp_configuration')
    return values


def message(event):
    if (set(event) - {'event', 'reason', 'resource', 'severity'} or event.get('event') not in EVENTS
            or event.get('reason', 'normal') not in REASONS
            or event.get('resource') not in {'stockage', 'sauvegardes', 'planification', 'horloge', 'test', 'conservation'}
            or event.get('severity') not in {'warning', 'critical', 'emergency', 'normal'}):
        raise NotificationError('invalid_notification_event')
    subject = 'DocuMind — ' + event['event'] + ' — ' + event['resource']
    body = '\n\n'.join((EVENTS[event['event']], REASONS[event.get('reason', 'normal')],
        'Consulter journalctl -u documind-monitor.service et le guide de récupération. '
        'Aucune action destructive n’a été exécutée par la surveillance.'))
    return subject, body


def send(event, path=CONFIG):
    subject, body = message(event)
    config = smtp_config(path)
    sender = getaddresses([config['ALERT_FROM']])
    recipients = getaddresses([config['ALERT_TO']])
    if len(sender) != 1 or not recipients or any(not re.fullmatch(r'[^@\s<>,]+@[^@\s<>,]+', addr) for _, addr in sender + recipients):
        raise NotificationError('invalid_smtp_addresses')
    mail = EmailMessage()
    mail['From'], mail['To'], mail['Subject'] = config['ALERT_FROM'], config['ALERT_TO'], subject
    mail.set_content(body)
    try:
        with smtplib.SMTP(config['SMTP_HOST'], int(config['SMTP_PORT']), timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
            smtp.login(config['SMTP_USERNAME'], config['SMTP_PASSWORD'])
            if smtp.send_message(mail, from_addr=sender[0][1], to_addrs=[addr for _, addr in recipients]):
                raise NotificationError('smtp_recipients_refused')
    except Exception:
        raise NotificationError('notification_delivery_failed') from None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--test', action='store_true')
    parser.add_argument('legacy_event', nargs='?', choices=['documind-backup-failed'])
    args = parser.parse_args()
    try:
        if args.test or args.legacy_event:
            event = {'event': 'test-notification' if args.test else args.legacy_event,
                     'resource': 'test' if args.test else 'sauvegardes', 'severity': 'normal' if args.test else 'critical'}
        else:
            raw = sys.stdin.read(4097)
            if len(raw) > 4096:
                raise NotificationError('invalid_notification_event')
            event = json.loads(raw)
        send(event)
        print('notification_sent')
        return 0
    except Exception:
        print('notification_failed')
        return 1


if __name__ == '__main__':
    sys.exit(main())

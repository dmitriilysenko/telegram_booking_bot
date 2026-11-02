from django.core.management.base import BaseCommand
from django.core.exceptions import ImproperlyConfigured
from bot_app.bot_logic import run_bot
from bot_app.exceptions import validate_bot_settings


class Command(BaseCommand):
    help = 'Запускает Telegram-бота для записи на занятия'

    def add_arguments(self, parser):
        parser.add_argument(
            '--debug',
            action='store_true',
            help='Включить режим отладки (подробные логи)',
        )
        parser.add_argument(
            '--skip-validation',
            action='store_true',
            help='Пропустить проверку настроек',
        )

    def handle(self, *args, **options):
        if options['debug']:
            import logging
            logging.basicConfig(level=logging.DEBUG)

        # ============================================
        # ПРОВЕРКА НАСТРОЕК (только для runbot)
        # ============================================
        if not options.get('skip_validation'):
            try:
                validate_bot_settings()
            except ImproperlyConfigured as e:
                self.stdout.write(self.style.ERROR(str(e)))
                return

        self.stdout.write(self.style.SUCCESS('🤖 Бот запущен...'))
        self.stdout.write('📌 Нажми Ctrl+C для остановки')

        try:
            run_bot()
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('🛑 Бот остановлен'))
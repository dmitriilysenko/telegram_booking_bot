from django.db import models

class User(models.Model):
    """Модель пользователя Telegram"""
    telegram_id = models.BigIntegerField(unique=True, verbose_name="Telegram ID")
    username = models.CharField(max_length=150, blank=True, null=True, verbose_name="Username")
    first_name = models.CharField(max_length=150, verbose_name="Имя")
    last_name = models.CharField(max_length=150, blank=True, null=True, verbose_name="Фамилия")
    registered_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата регистрации")

    def __str__(self):
        return f"{self.first_name} {self.last_name or ''}".strip()

    class Meta:
        verbose_name = "Участник"
        verbose_name_plural = "Участники"


class Booking(models.Model):
    """Модель записи на занятие"""
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='bookings',
        verbose_name="Пользователь"
    )
    date = models.DateField(verbose_name="Дата занятия")
    time = models.TimeField(verbose_name="Время занятия")
    is_active = models.BooleanField(default=True, verbose_name="Активна")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    def __str__(self):
        return f"{self.user} — {self.date} {self.time.strftime('%H:%M')}"

    class Meta:
        verbose_name = "Запись"
        verbose_name_plural = "Записи"
        # Защита от дублей: пользователь не может записаться дважды на одно время
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'date', 'time'],
                condition=models.Q(is_active=True),
                name='unique_active_booking'
            )
        ]
        ordering = ['date', 'time']
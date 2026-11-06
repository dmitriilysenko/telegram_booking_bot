from django.db import models

class User(models.Model):
    """Модель пользователя Telegram"""
    telegram_id = models.BigIntegerField(unique=True, verbose_name="Telegram ID")
    username = models.CharField(max_length=150, blank=True, null=True, verbose_name="Username")
    first_name = models.CharField(max_length=150, verbose_name="Имя")
    last_name = models.CharField(max_length=150, blank=True, null=True, verbose_name="Фамилия")
    display_name = models.CharField(
        max_length=150, blank=True, default='', verbose_name='Отображаемое имя'
    )
    gender = models.CharField(
        max_length=1,
        choices=(('M', 'Парень'), ('F', 'Девушка')),
        blank=True, default='', verbose_name='Пол',
    )
    is_airsoft_member = models.BooleanField(
        default=False, verbose_name='Состоит в airsoft-группе'
    )
    is_staff = models.BooleanField(default=False, verbose_name='Админ')
    is_trainer = models.BooleanField(default=False, verbose_name='Тренер')
    registered_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата регистрации')

    def __str__(self):
        return self.display_name or f'{self.first_name} {self.last_name or ""}'.strip()

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
        constraints = (
            models.UniqueConstraint(
                fields=['user', 'date', 'time'],
                condition=models.Q(is_active=True),
                name='unique_active_booking'
            ),
        )
        ordering = ('date', 'time')


class Review(models.Model):
    """Отзыв о работе бота"""
    user = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='reviews', verbose_name='Пользователь',
    )
    text = models.TextField(verbose_name='Отзыв')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата')

    def __str__(self):
        return f'{self.user}: {self.text[:50]}'

    class Meta:
        verbose_name = 'Отзыв'
        verbose_name_plural = 'Отзывы'
        ordering = ('-created_at',)


class AirsoftTraining(models.Model):
    """
    Airsoft-тренировка (одна на группу в неделю).

    Статус меняет тренер (is_trainer) через бот:
    - pending   — тренер ещё не подтвердил
    - confirmed — тренировка подтверждена
    - cancelled — тренировка отменена
    """
    GENDER_CHOICES = (('M', 'Парни'), ('F', 'Девушки'))
    STATUS_CHOICES = (
        ('pending', 'Тренировка не подтверждена'),
        ('confirmed', 'Тренировка подтверждена'),
        ('cancelled', 'Тренировка отменена'),
    )
    gender = models.CharField(
        max_length=1, choices=GENDER_CHOICES, verbose_name='Группа'
    )
    week_start = models.DateField(verbose_name='Неделя')
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default='pending',
        verbose_name='Статус',
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.get_gender_display()} — {self.week_start} — {self.get_status_display()}'

    class Meta:
        verbose_name = 'Airsoft-тренировка'
        verbose_name_plural = 'Airsoft-тренировки'
        constraints = (
            models.UniqueConstraint(
                fields=('gender', 'week_start'),
                name='unique_airsoft_training',
            ),
        )
        ordering = ('week_start', 'gender')


class AirsoftConfirmation(models.Model):
    """
    Подтверждение участия участника в airsoft-тренировке.

    gender фиксирует группу на момент подтверждения (если тренер
    позже поменяет user.gender — история сохранится).
    """
    user = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='airsoft_confirmations', verbose_name='Пользователь',
    )
    week_start = models.DateField(verbose_name='Неделя')
    gender = models.CharField(
        max_length=1,
        choices=(('M', 'Парни'), ('F', 'Девушки')),
        verbose_name='Группа',
    )
    confirmed = models.BooleanField(default=False, verbose_name='Подтверждено')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        status = '✅' if self.confirmed else '❌'
        return f'{self.user} — {self.week_start} — {self.get_gender_display()} — {status}'

    class Meta:
        verbose_name = 'Подтверждение airsoft'
        verbose_name_plural = 'Подтверждения airsoft'
        constraints = (
            models.UniqueConstraint(
                fields=('user', 'week_start', 'gender'),
                name='unique_airsoft_confirmation',
            ),
        )
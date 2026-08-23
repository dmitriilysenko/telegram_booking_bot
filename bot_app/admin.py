from django.contrib import admin
from .models import User, Booking


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    """Админка для модели User"""
    list_display = ('id', 'telegram_id', 'username', 'first_name', 'last_name', 'registered_at')
    list_filter = ('registered_at',)
    search_fields = ('telegram_id', 'username', 'first_name', 'last_name')
    readonly_fields = ('registered_at',)
    ordering = ('-registered_at',)

    fieldsets = (
        ('Основная информация', {
            'fields': ('telegram_id', 'username', 'first_name', 'last_name')
        }),
        ('Дата регистрации', {
            'fields': ('registered_at',),
            'classes': ('collapse',)  # Сворачиваемый блок
        }),
    )


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    """Админка для модели Booking"""
    list_display = ('id', 'user', 'date', 'time', 'is_active', 'created_at')
    list_filter = ('is_active', 'date', 'time')
    search_fields = ('user__telegram_id', 'user__username', 'user__first_name', 'user__last_name')
    readonly_fields = ('created_at',)
    ordering = ('-date', '-time')

    fieldsets = (
        ('Запись', {
            'fields': ('user', 'date', 'time', 'is_active')
        }),
        ('Дата создания', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )

    # Действия для массовых операций
    actions = ['mark_as_active', 'mark_as_inactive']

    def mark_as_active(self, request, queryset):
        """Активные записи"""
        updated = queryset.update(is_active=True)
        self.message_user(request, f"Активировано {updated} записей")

    mark_as_active.short_description = "Активировать выбранные записи"

    def mark_as_inactive(self, request, queryset):
        """Деактивировать записи"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f"Деактивировано {updated} записей")

    mark_as_inactive.short_description = "Деактивировать выбранные записи"
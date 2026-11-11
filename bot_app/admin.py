from django.contrib import admin

from .models import (
    User, Booking, Review, AirsoftTraining, AirsoftConfirmation,
)


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'telegram_id', 'display_name', 'username',
        'last_name', 'first_name', 'patronymic', 'position', 'gender',
        'is_airsoft_member', 'is_staff', 'is_trainer',
    )
    list_filter = ('is_airsoft_member', 'gender', 'is_staff', 'is_trainer')
    search_fields = ('telegram_id', 'username', 'display_name', 'first_name', 'last_name')
    list_editable = ('is_airsoft_member', 'is_staff', 'is_trainer')
    readonly_fields = ('registered_at',)
    ordering = ('-registered_at',)
    fieldsets = (
        ('Основная информация', {
            'fields': (
                'telegram_id', 'username', 'last_name', 'first_name',
                'patronymic', 'display_name', 'position', 'birth_date',
                'gender',
            ),
        }),
        ('Флаги', {
            'fields': ('is_airsoft_member', 'is_staff', 'is_trainer'),
        }),
        ('Дата регистрации', {
            'fields': ('registered_at',),
            'classes': ('collapse',),
        }),
    )


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'date', 'time', 'is_active', 'created_at')
    list_filter = ('is_active', 'date', 'time')
    search_fields = ('user__telegram_id', 'user__display_name', 'user__username')
    readonly_fields = ('created_at',)
    ordering = ('-date', '-time')
    actions = ('mark_as_active', 'mark_as_inactive')

    @admin.action(description='Активировать')
    def mark_as_active(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'Активировано {updated}')

    @admin.action(description='Деактивировать')
    def mark_as_inactive(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'Деактивировано {updated}')


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'text', 'decision', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('user__display_name', 'text', 'decision')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)
    fieldsets = (
        ('Отзыв', {
            'fields': ('user', 'text', 'created_at'),
        }),
        ('Модерация', {
            'fields': ('decision', 'is_active'),
        }),
    )


@admin.register(AirsoftTraining)
class AirsoftTrainingAdmin(admin.ModelAdmin):
    list_display = ('id', 'gender', 'week_start', 'status', 'updated_at')
    list_filter = ('status', 'gender', 'week_start')
    search_fields = ('week_start',)
    readonly_fields = ('updated_at',)
    ordering = ('-week_start', 'gender')


@admin.register(AirsoftConfirmation)
class AirsoftConfirmationAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'week_start', 'gender', 'confirmed', 'created_at')
    list_filter = ('confirmed', 'gender', 'week_start')
    search_fields = ('user__display_name', 'user__telegram_id')
    readonly_fields = ('created_at',)
    ordering = ('-week_start', 'gender', 'user')
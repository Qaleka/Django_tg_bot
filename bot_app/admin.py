from django.contrib import admin
from .models import User, Group, Student, Teacher, Event, EventGroup, StudentSubmission

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('username', 'telegram_id', 'firstname', 'secondName', 'middlename', 'is_staff')
    search_fields = ('username', 'telegram_id')

@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ('name',)

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('user', 'group')
    search_fields = ('user__username',)

@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ('user',)
    search_fields = ('user__username',)

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('title', 'date', 'teacher', 'recurrence', 'reminder_sent')
    list_filter = ('recurrence', 'date')
    search_fields = ('title', 'description')

@admin.register(EventGroup)
class EventGroupAdmin(admin.ModelAdmin):
    list_display = ('event', 'group')

@admin.register(StudentSubmission)
class StudentSubmissionAdmin(admin.ModelAdmin):
    list_display = ('student', 'teacher', 'created_at')
    search_fields = ('student__user__username', 'teacher__user__username')

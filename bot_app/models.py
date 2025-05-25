from django.contrib.auth.models import User
from django.utils.timezone import now
from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    telegram_id = models.CharField(max_length=255, null=True, blank=True, unique=True)
    firstname = models.CharField(max_length=255, null=True, blank=True)
    secondName = models.CharField(max_length=255, null=True, blank=True)
    middlename = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return self.username

    def get_full_name(self):
        parts = [self.secondName, self.firstname, self.middlename]
        return " ".join(p for p in parts if p)

class Group(models.Model):
    """Группа студентов"""
    name = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.name


class Student(models.Model):
    """Модель студента"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student')
    group = models.ForeignKey('Group', on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} ({self.group.name if self.group else 'Без группы'})"


class Teacher(models.Model):
    """Модель преподавателя"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='teacher')

    def __str__(self):
        return f"{self.user.username} (Преподаватель)"


class Event(models.Model):
    """Модель события"""
    RECURRENCE_CHOICES = [
        ('none', 'Без повторения'),
        ('daily', 'Ежедневно'),
        ('weekly', 'Еженедельно'),
        ('biweekly', 'Раз в 2 недели'),
        ('monthly', 'Ежемесячно'),
    ]

    title = models.CharField(max_length=255)
    description = models.TextField()
    date = models.DateTimeField(default=now)
    teacher = models.ForeignKey('Teacher', on_delete=models.CASCADE, related_name="created_events")
    file = models.FileField(upload_to='event_files/', null=True, blank=True)
    reminder_sent = models.BooleanField(default=False)
    groups = models.ManyToManyField('Group', through='EventGroup', related_name='events')
    recurrence = models.CharField(max_length=10, choices=RECURRENCE_CHOICES, default='none')
    def __str__(self):
        return f"{self.title} - {self.date}"


class EventGroup(models.Model):
    """Промежуточная таблица для связи событий и групп студентов"""
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    group = models.ForeignKey(Group, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.event.title} -> {self.group.name}"

class StudentSubmission(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE)
    description = models.TextField()
    file = models.FileField(upload_to='submissions/')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Отправка от {self.student.user.username} -> {self.teacher.user.username}"

class EventResponse(models.Model):
    RESPONSE_CHOICES = [
        ('yes', 'Приду'),
        ('no', 'Не приду'),
        ('pending', 'Нет ответа')
    ]

    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    response = models.CharField(max_length=10, choices=RESPONSE_CHOICES, default='pending')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('event', 'student')

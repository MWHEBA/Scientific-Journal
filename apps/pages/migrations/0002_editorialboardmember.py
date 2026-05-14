from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='EditorialBoardMember',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('name',        models.CharField(max_length=255, verbose_name='الاسم')),
                ('role',        models.CharField(
                    choices=[
                        ('editor_in_chief', 'رئيس التحرير'),
                        ('deputy_editor',   'نائب رئيس التحرير'),
                        ('regional_editor', 'رئيس تحرير إقليمي'),
                        ('supervisory',     'عضو اللجنة الإشرافية'),
                        ('editorial',       'عضو هيئة التحرير'),
                    ],
                    default='editorial',
                    max_length=30,
                    verbose_name='الدور',
                )),
                ('institution', models.CharField(blank=True, max_length=255, verbose_name='المؤسسة')),
                ('country',     models.CharField(blank=True, max_length=100, verbose_name='الدولة')),
                ('email',       models.EmailField(blank=True, max_length=254, verbose_name='البريد الإلكتروني')),
                ('order',       models.PositiveSmallIntegerField(default=0, verbose_name='الترتيب')),
                ('is_active',   models.BooleanField(default=True, verbose_name='نشط')),
            ],
            options={
                'verbose_name': 'عضو هيئة التحرير',
                'verbose_name_plural': 'هيئة التحرير',
                'ordering': ['order', 'name'],
            },
        ),
    ]

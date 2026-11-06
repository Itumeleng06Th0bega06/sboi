import django.core.validators
import django.db.models.deletion
import sboi.storage
from django.conf import settings
from django.db import migrations, models

import members.models_comms


class Migration(migrations.Migration):

    dependencies = [
        ('members', '0006_commspost_commscomment_commsreaction'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RenameField(
            model_name='commspost',
            old_name='kind',
            new_name='audience',
        ),
        migrations.RenameField(
            model_name='commspost',
            old_name='created_by',
            new_name='author',
        ),
        migrations.RenameField(
            model_name='commspost',
            old_name='published',
            new_name='is_published',
        ),
        migrations.AddField(
            model_name='commspost',
            name='is_hidden',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='commspost',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, db_index=True),
        ),
        migrations.AlterModelOptions(
            name='commspost',
            options={'ordering': ['-created_at', '-pk']},
        ),
        migrations.AlterModelOptions(
            name='commscomment',
            options={'ordering': ['created_at', 'pk']},
        ),
        migrations.AlterUniqueTogether(
            name='commsreaction',
            unique_together=set(),
        ),
        migrations.AddConstraint(
            model_name='commsreaction',
            constraint=models.UniqueConstraint(
                fields=('post', 'user', 'reaction'),
                name='unique_feed_reaction',
            ),
        ),
        migrations.CreateModel(
            name='CommsAttachment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file', models.FileField(storage=sboi.storage.PrivateMediaStorage(), upload_to=members.models_comms.feed_upload_path, validators=[django.core.validators.FileExtensionValidator(('pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'csv', 'rtf', 'odt', 'ods', 'jpg', 'jpeg', 'png', 'gif', 'webp', 'mp4', 'webm', 'mov', 'm4v'))])),
                ('original_name', models.CharField(max_length=255)),
                ('content_type', models.CharField(blank=True, max_length=120)),
                ('size', models.PositiveIntegerField(default=0)),
                ('kind', models.CharField(choices=[('image', 'Image'), ('video', 'Video'), ('document', 'Document')], default='document', max_length=12)),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
                ('post', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attachments', to='members.commspost')),
            ],
            options={
                'ordering': ['pk'],
            },
        ),
    ]

# Amazon Transcribe custom vocabularies (A5).
#
# Optional (enable_transcribe_custom_vocabulary). Biases streaming recognition
# toward domain terms and proper nouns so transcripts — and therefore the
# translation and meeting notes downstream — are more accurate. Custom
# vocabularies are per-language; LiveCap runs parallel vi-VN and en-US streams,
# so one vocabulary is created for each. Using a vocabulary in streaming needs
# no extra task-role IAM (it is covered by StartStreamTranscription); creating
# the vocabularies here is an admin/Terraform action.
#
# Vietnamese note: Vietnamese custom-vocabulary phrases use a specific character
# set (tones written as numbers). Keep tech/proper-noun entries (ASCII) here and
# add toned Vietnamese phrases per the AWS charset doc:
# https://docs.aws.amazon.com/transcribe/latest/dg/charsets.html

variable "enable_transcribe_custom_vocabulary" {
  description = "Create Amazon Transcribe custom vocabularies (vi + en) and pass their names to the backend task."
  type        = bool
  default     = true
}

variable "transcribe_vocabulary_phrases_en" {
  description = "English custom-vocabulary phrases. Multi-word phrases must be hyphenated (e.g. Amazon-Transcribe)."
  type        = list(string)
  default = [
    "LiveCap",
    "Amazon-Transcribe",
    "Amazon-Translate",
    "Amazon-Bedrock",
    "CloudFront",
    "Fargate",
    "DynamoDB",
  ]
}

variable "transcribe_vocabulary_phrases_vi" {
  description = "Vietnamese custom-vocabulary phrases. Toned words must follow the Transcribe Vietnamese charset (tones as numbers)."
  type        = list(string)
  default = [
    "LiveCap",
    "CloudFront",
    "Fargate",
    "DynamoDB",
  ]
}

resource "aws_transcribe_vocabulary" "en" {
  count = var.enable_transcribe_custom_vocabulary ? 1 : 0

  vocabulary_name = "${var.project_name}-en-${var.environment}"
  language_code   = "en-US"
  phrases         = var.transcribe_vocabulary_phrases_en

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-en-${var.environment}"
      Environment = var.environment
    }
  )
}

resource "aws_transcribe_vocabulary" "vi" {
  count = var.enable_transcribe_custom_vocabulary ? 1 : 0

  vocabulary_name = "${var.project_name}-vi-${var.environment}"
  language_code   = "vi-VN"
  phrases         = var.transcribe_vocabulary_phrases_vi

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-vi-${var.environment}"
      Environment = var.environment
    }
  )
}

locals {
  # Vocabulary names passed to the task (empty when disabled). Referencing the
  # resources establishes an apply-time dependency so the task definition is
  # updated after the vocabularies reach READY.
  transcribe_vocabulary_name_en = var.enable_transcribe_custom_vocabulary ? one(aws_transcribe_vocabulary.en[*].vocabulary_name) : ""
  transcribe_vocabulary_name_vi = var.enable_transcribe_custom_vocabulary ? one(aws_transcribe_vocabulary.vi[*].vocabulary_name) : ""
}

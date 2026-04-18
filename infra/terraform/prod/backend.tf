terraform {
  backend "s3" {
    bucket  = "nurihaus-terraform-state"
    key     = "devopsim/prod/terraform.tfstate"
    region  = "ap-northeast-2"
    profile = "devopsim"
  }
}

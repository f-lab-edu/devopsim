terraform {
  backend "s3" {
    bucket  = "nurihaus-terraform-state"
    key     = "devopsim/terraform.tfstate"
    region  = "ap-northeast-2"
    profile = "devopsim"
  }
}
